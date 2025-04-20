# src/ai_player.py
import random
import os
import asyncio
import re
# --- ADDED json and ValidationError ---
import json
from pydantic import ValidationError
# -----------------------------------
# --- Added Union for return type ---
# --- ADDED SpeechOutput schema ---
from typing import Optional, Any, Dict, List, Type, Union
from src.ai_schemas import SpeechOutput # Import the updated schema
# ---------------------------------
import logging

# Import ActionContext Literals etc.
from src.state import ActionContext, GraphState, Literal
from src.llm_interface import get_llm_response_string


# # --- !!! TEMPORARY DEBUG FLAG !!! ---
# DEBUG_FORCE_PARSE_FAILURE = True # Set to True to enable, False to disable
# DEBUG_TARGET_PLAYER = "Alice"    # Which player to affect
# DEBUG_TARGET_ACTION = "vote"   # Which action to affect
# # ------------------------------------



# --- Constants ---
RECENT_LOG_COUNT = 3

# --- Prompts and Context ---
BASE_PROMPT_DIR = os.path.join(os.path.dirname(__file__), 'prompts')
def load_base_prompt(role: str) -> str:
    # Added Investigator role mapping
    role_map = {'Imp': 'impostor', 'Villager': 'villager', 'Investigator': 'investigator'}
    filename = role_map.get(role, 'villager') + '.txt' # Default to villager if role unknown
    filepath = os.path.join(BASE_PROMPT_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logging.warning(f"Base prompt file not found for role '{role}' at {filepath}. Using default.")
        # Provide a generic default based on role name
        return f"You are Player {{player_id}}. Your role is {role}. Your goal depends on your role's objectives."
    except Exception as e:
        logging.error(f"Error loading prompt for role '{role}': {e}")
        return f"You are Player {{player_id}}. Your role is {role}. Your goal depends on your role's objectives."


def _build_dynamic_context(
    game_state: GraphState,
    player_id_for_context: str,
    player_role_for_context: Optional[str]
    ) -> str:
    # This function remains the same as before
    try:
        # --- Extracting Base Information ---
        round_num = game_state.get('round_number', 0)
        alive_players = game_state.get('alive_players', [])
        public_log = game_state.get('public_log', [])
        previous_votes = game_state.get('previous_round_votes', {})

        # --- Get Last Night's Victim (from state) ---
        victim_info = game_state.get('last_victim')
        victim_display = victim_info if victim_info else "None confirmed"
        logging.debug(f"Context: Retrieved last_victim from state: {victim_info}")

        # --- Get Last Executed Player (from state) ---
        executed_info = game_state.get('last_executed')
        prev_round_num = round_num - 1
        if executed_info:
            if "None" in executed_info: executed_display = executed_info
            else: executed_display = executed_info
        elif round_num > 1: executed_display = "None (Not yet determined or Error)"
        else: executed_display = "N/A (Round 1)"
        logging.debug(f"Context: Retrieved last_executed from state: {executed_info}")

        # --- Format the Public Context String ---
        context_str = f"\n--- Current Situation (Round {round_num}) ---\n"
        context_str += f"Alive Players ({len(alive_players)}): {', '.join(sorted(alive_players))}\n"
        context_str += f"Last Night's Victim: {victim_display}\n"
        context_str += f"Last Executed Player (End of Round {prev_round_num if prev_round_num > 0 else 'N/A'}): {executed_display}\n"

        # --- Format Previous Votes (public) ---
        if previous_votes:
            context_str += f"\nPrevious Vote Breakdown (Round {prev_round_num}):\n"
            # --- MODIFIED: Include intent/target if available in log format ---
            # Assuming log format might become richer, adapt if needed.
            # For now, just display basic votes from previous_round_votes dict
            vote_list = [f"  - {voter} voted for {target}" for voter, target in previous_votes.items()]
            # --------------------------------------------------------------
            if vote_list: context_str += "\n".join(vote_list) + "\n"
            else: context_str += "  (No votes cast this round or voters died)\n"
        elif round_num > 1:
             context_str += f"\nPrevious Vote Breakdown (Round {prev_round_num}):\n  (No votes recorded for previous round)\n"

        # --- Format Recent Log Snippet (public) ---
        log_tail = public_log[-RECENT_LOG_COUNT:]
        if log_tail:
             # --- Simplify cleaning, assume log contains player: {json} or SYS/GM messages ---
             cleaned_log_tail = []
             for L in log_tail:
                 # Attempt to extract JSON if it looks like player speech
                 match = re.match(r"(\w+):\s*(\{.*?\})", L) # Basic match for PlayerID: {json}
                 if match:
                     player_id_log = match.group(1)
                     try:
                         speech_data = json.loads(match.group(2))
                         content = speech_data.get('speech_content', '[Speech Content Missing]')
                         intent = speech_data.get('intent')
                         target = speech_data.get('target_player')
                         target_str = f" (-> {target})" if target else ""
                         intent_str = f" [{intent}]" if intent else ""
                         cleaned_log_tail.append(f"{player_id_log}{intent_str}{target_str}: \"{content}\"")
                     except json.JSONDecodeError:
                         # Fallback if JSON is invalid
                         cleaned_log_tail.append(re.sub(r'\[/?(?:bold|italic|color|dim|strike|underline|blink|reverse|conceal|code|on\s+\w+|[a-z]+(?: on \w+)?|/?rule)\]', '', L))
                 else:
                     # For non-JSON logs (SYS, GM, older formats), keep basic cleaning
                     cleaned_line = re.sub(r'\[/?(?:bold|italic|color|dim|strike|underline|blink|reverse|conceal|code|on\s+\w+|[a-z]+(?: on \w+)?|/?rule)\]', '', L)
                     cleaned_line = re.sub(r"^(SYS|VOTE|SPEAK|VOTE_REVEAL|DIM|NARRATOR|GM): ", "", cleaned_line).strip()
                     cleaned_log_tail.append(cleaned_line)
             # ------------------------------------------------------------------------
             context_str += f"\nRecent Events Log (Last {RECENT_LOG_COUNT}):\n" + "\n".join([f"- {L}" for L in cleaned_log_tail]) + "\n"

        # --- ADD PRIVATE CONTEXT (if applicable) ---
        private_context_str = ""
        if player_role_for_context == 'Investigator':
            pending_results = game_state.get('pending_night_results', {})
            investigator_results = pending_results.get(player_id_for_context, {})
            investigation_info = investigator_results.get('investigation')

            if investigation_info:
                private_context_str += f"\n--- Your Private Information ---\n"
                cleaned_investigation_info = re.sub(r'\[/?(?:bold|color|green|magenta)\]', '', investigation_info)
                private_context_str += f"- Last Night's Investigation Result: {cleaned_investigation_info}\n"
                private_context_str += f"--- End Private Information ---\n"
                logging.debug(f"Context: Added private Investigator result for {player_id_for_context}")
            else:
                logging.debug(f"Context: No pending investigation result found for Investigator {player_id_for_context}")

        # Combine public and private context
        full_context_str = context_str + private_context_str + "--- End Situation ---\n"

        logging.debug(f"Generated context for AI ({player_id_for_context}):\n{full_context_str}")
        return full_context_str

    except Exception as e:
        logging.error(f"Error building dynamic context for {player_id_for_context}: {e}", exc_info=True)
        return "\n--- Current Situation ---\nError generating context. Please proceed with caution.\n--- End Situation ---\n"


def _format_task_prompt(context: ActionContext) -> str:
    # This function remains the same as before
    action_type = context['action_type']
    options = context.get('options')
    prompt_msg = context.get('prompt_message', f"Your task is to perform the '{action_type}' action.")
    task_str = f"\n--- Your Task ---\n{prompt_msg}\n"
    if options:
        task_str += "Available Options:\n" + "\n".join([f"  {k}: {v}" for k, v in options.items()]) + "\n"
        task_str += "\n**IMPORTANT: Reply with ONLY the numerical key (e.g., '1', '2', '3') corresponding to your choice AND a brief reasoning.**" # Assume reasoning is part of BaseTargetSelection schema if needed
        task_str += "\n**Do NOT add explanations, commentary, or conversational text like 'Okay' or 'I choose'.**"
    elif action_type == 'speak':
         # Prompt now asks for JSON output (matching instructions in agent prompts)
         task_str += "\n**IMPORTANT: Reply ONLY with the JSON object representing your speech action, matching the required `SpeechOutput` schema.**"
         task_str += "\n**Ensure the JSON is valid. Do not add introductions like 'My speech is:' or conversational text outside the JSON.**"
         task_str += "\n```json\n{\n  \"speech_content\": \"...\",\n  \"intent\": \"...\",\n  \"target_player\": \"... or null\",\n  \"tone\": \"...\"\n}\n```" # Added example structure
    task_str += "\n--- End Task ---\n"
    return task_str


# --- Placeholder Functions (REMAIN HERE FOR NOW, GM Handler might call them later) ---
def _placeholder_ai_kill(options: Optional[Dict[str, str]]) -> Optional[str]:
     if not options: logging.warning("Placeholder kill: no options."); return None
     chosen_key = random.choice(list(options.keys()))
     target_id = options.get(chosen_key, "?")
     logging.info(f"[Placeholder Fallback] AI Imp randomly chose target: {target_id} (Key: {chosen_key}).")
     # Placeholder should ideally return a structure matching KillDecision if used directly
     # For now, just the key is expected by the GM handler if it needs to fallback
     return chosen_key

def _placeholder_ai_speak(context: ActionContext) -> Optional[Dict]: # Return Dict matching SpeechOutput
     player_id = context['player_id']
     role = context.get('player_role', 'Unknown')
     # Placeholder speech now generates a compliant JSON object
     speech_content = f"Player {player_id} ({role}) seems unable to speak clearly at this moment."
     speech_output = {
         "speech_content": speech_content,
         "intent": "general_statement", # Or perhaps a specific 'failure' intent?
         "target_player": None,
         "tone": "neutral"
     }
     logging.info(f"[Placeholder Fallback] AI generated speech object: {speech_output}")
     # Validate against schema before returning (good practice)
     try:
         validated_output = SpeechOutput.model_validate(speech_output)
         return validated_output.model_dump() # Return as dict
     except ValidationError:
         logging.error("[Placeholder Fallback] Error validating placeholder speech output.")
         # Return a minimal valid dict if validation fails somehow
         return {"speech_content": "Error generating fallback speech.", "intent": "general_statement", "target_player": None, "tone": "neutral"}


def _placeholder_ai_vote(options: Optional[Dict[str, str]]) -> Optional[str]:
    if not options: logging.warning("Placeholder vote: no options."); return None
    chosen_key = random.choice(list(options.keys()))
    target_id = options.get(chosen_key, "?")
    logging.info(f"[Placeholder Fallback] AI randomly voted for: {target_id} (Key: {chosen_key}).")
    # Placeholder should ideally return a structure matching VoteDecision if used directly
    return chosen_key

def _placeholder_ai_investigate(options: Optional[Dict[str, str]]) -> Optional[str]:
    if not options: logging.warning("Placeholder investigate: no options."); return None
    chosen_key = random.choice(list(options.keys()))
    target_id = options.get(chosen_key, "?")
    logging.info(f"[Placeholder Fallback] AI Investigator randomly chose target: {target_id} (Key: {chosen_key}).")
    # Placeholder should ideally return a structure matching InvestigateDecision if used directly
    return chosen_key
# -----------------------------------------------------------------------------------


# --- Central AI Decision Logic (MODIFIED for Speech JSON Output) ---
# --- Return type changed to Union[Optional[Any], Dict] ---
async def get_ai_decision_logic(context: ActionContext) -> Union[Optional[Any], Dict]:
    """
    Orchestrates AI decision: Gets LLM response, attempts parsing based on action_type.
    For 'speak', expects JSON conforming to SpeechOutput schema.
    If parsing/validation fails, returns a failure dictionary.
    If LLM call itself fails, returns failure dictionary.
    """
    action_type = context['action_type']
    player_id = context['player_id']
    role = context.get('player_role', 'Unknown')
    options = context.get('options')
    full_game_state = context['full_game_state']

    system_prompt = load_base_prompt(role).format(player_id=player_id)
    dynamic_context_str = _build_dynamic_context(
        game_state=full_game_state,
        player_id_for_context=player_id,
        player_role_for_context=role
    )
    task_prompt_str = _format_task_prompt(context)
    user_prompt = f"{dynamic_context_str}\n{task_prompt_str}"

    should_stream = (action_type == 'speak') # Keep streaming for 'speak'
    llm_response_str: Optional[str] = await get_llm_response_string(
         system_prompt=system_prompt,
         user_prompt=user_prompt,
         player_id=player_id,
         enable_streaming=should_stream
    )

    # --- Handle LLM call failure FIRST ---
    if llm_response_str is None:
        logging.error(f"LLM call failed for {player_id} ({action_type}). Returning failure signal.")
        return {
            'status': 'llm_call_failed',
            'raw_output': None, # No output received
            'intended_action': action_type,
            'options': options,
            'player_id': player_id
        }
    # -----------------------------------------

    # --- Processing Logic (Attempt Parsing) ---
    final_output: Optional[Any] = None # Can be string (key) or dict (speech)
    # Basic cleaning (especially important before JSON parsing)
    response_str = llm_response_str.strip()
    # Try to find JSON block even if surrounded by ``` or other text
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_str, re.DOTALL | re.IGNORECASE)
    if json_match:
        response_str = json_match.group(1).strip()
        logging.info(f"  Extracted potential JSON block from response.")
    else:
        # If no ```json``` block, assume the whole cleaned response might be the JSON
        # Further cleaning might be needed depending on LLM habits
        response_str = re.sub(r"^(okay|alright|sure|here is|here's|my speech is|as requested)[,.:]?\s*", "", response_str, flags=re.IGNORECASE)
        response_str = response_str.strip('`').strip() # Remove potential backticks

    logging.info(f"Processing LLM response for {player_id} ({action_type}). Raw: '{llm_response_str[:150]}...'")
    logging.info(f"  Cleaned/Extracted Response for Parsing: '{response_str[:150]}...'")


    # --- MODIFIED: Handle 'speak' Action (Expect JSON) ---
    if action_type == 'speak':
        logging.debug(f"  Attempting to parse JSON and validate SpeechOutput from: '{response_str}'")
        parsed_dict = None
        validation_error = None
        try:
            parsed_dict = json.loads(response_str)
            logging.debug(f"    JSON parsing successful.")
            try:
                validated_output = SpeechOutput.model_validate(parsed_dict)
                final_output = validated_output.model_dump() # Store as dict
                logging.info(f"    Successfully parsed and validated SpeechOutput for {player_id}.")
            except ValidationError as e:
                validation_error = e
                logging.warning(f"    SpeechOutput validation failed for {player_id}: {e}")
                final_output = None # Validation failed
        except json.JSONDecodeError as e:
            logging.warning(f"    JSON parsing failed for {player_id}: {e}")
            final_output = None # Parsing failed
        except Exception as e: # Catch any other unexpected errors during parsing/validation
             logging.error(f"    Unexpected error during speech parsing/validation for {player_id}: {e}", exc_info=True)
             final_output = None

        # Check if essential content is present even if validation passed superficially
        if isinstance(final_output, dict) and not final_output.get('speech_content', '').strip():
             logging.warning(f"  Validated SpeechOutput for {player_id} has empty 'speech_content'. Treating as failure.")
             final_output = None # Treat empty content as failure

    # --- Handle Key-Based Actions (vote, imp_kill, investigate) ---
    elif action_type in ['vote', 'imp_kill', 'investigate'] and options:
        logging.debug(f"  Attempting to parse key from cleaned response: '{response_str}' for action {action_type}")
        # Existing key parsing logic remains here...
        found_key = None
        potential_keys = list(options.keys())
        # 1. Direct Match
        if response_str in potential_keys:
            found_key = response_str
            logging.info(f"  Successfully parsed key via direct match: {found_key}")
        # 2. Regex for standalone key
        else:
             keys_pattern = r'(?<!\d)(' + '|'.join(re.escape(k) for k in potential_keys) + r')(?!\d)'
             match = re.search(keys_pattern, response_str)
             if match:
                 key_candidate = match.group(1)
                 if re.fullmatch(r"[\s\.,!\"'\(]*" + re.escape(key_candidate) + r"[\s\.,!\"'\)]*", response_str, re.IGNORECASE):
                      found_key = key_candidate
                      logging.info(f"  Successfully parsed key via regex (standalone full match): {found_key}")
                 else:
                      logging.warning(f"  Regex found key '{key_candidate}' but it's part of larger/ambiguous text ('{response_str}'). Considered parsing failure.")
                      found_key = None
             else:
                  logging.warning(f"  Could not find any potential key ({potential_keys}) in response '{response_str}' using regex.")
                  found_key = None

        if found_key:
            final_output = found_key # Store the key string
        else:
            # Logging for key parsing failure...
            if response_str in potential_keys:
                 logging.error(f"  Logic Error: Direct match key '{response_str}' was somehow missed.")
            elif match and not re.fullmatch(r"[\s\.,!\"'\(]*" + re.escape(match.group(1)) + r"[\s\.,!\"'\)]*", response_str, re.IGNORECASE):
                 logging.warning(f"  Could not parse key: Ambiguous key '{match.group(1)}' found within larger text '{response_str}'. Options: {potential_keys}.")
            else:
                 logging.warning(f"  Could not parse key: No valid key found in response '{response_str}'. Options: {potential_keys}.")
            final_output = None # Parsing failed

    # --- Handle Other/Unknown Action Types ---
    else:
        logging.warning(f"No specific parsing logic defined or options missing for action '{action_type}'. Raw (cleaned): '{response_str}'. Considered parsing failure.")
        final_output = None

    # --- Final Return Logic ---
    if final_output is None:
        # PARSING/VALIDATION FAILED or LLM returned unusable content
        logging.warning(f"LLM response parsing/validation failed for {player_id} ({action_type}). Returning failure signal.")
        failure_details = {
            'status': 'parsing_failed',
            'raw_output': llm_response_str, # Original LLM output
            'cleaned_output': response_str, # Cleaned/extracted version used for parsing
            'intended_action': action_type,
            'options': options,
            'player_id': player_id
        }
        # Add specific error details if available
        if action_type == 'speak':
             if validation_error: failure_details['error_details'] = str(validation_error)
             elif 'JSONDecodeError' in str(e) if 'e' in locals() else False : failure_details['error_details'] = "Invalid JSON format."
             else: failure_details['error_details'] = "Unknown parsing/validation error."

        return failure_details
    else:
        # Parsing/Validation was successful
        logging.info(f"Successfully parsed decision for {player_id} ({action_type}). Output Type: {type(final_output)}")
        # Return the successfully parsed key string or speech dict/object
        return final_output
    # --- End Modified Return Logic ---