# src/gm_utils.py
"""
Utilities for the Game Master (GM) / Narrator, including handling
agent decision failures and providing narrative interventions.
GM attempts to interpret ambiguous key-based responses.
"""
import logging
import random
import re # For key extraction
# --- REMOVED asyncio import --- No longer needed here
from typing import Dict, Any, Optional, Union

# Import state type hints
from .state import GraphState, PlayerState, ActionContext

# --- REMOVED local get_decision import --- No longer needed here

# --- Import schemas locally if needed for validation (unlikely here now) ---
# from src.ai_schemas import SpeechOutput
# from pydantic import ValidationError

# --- Import console ---
try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console() # Fallback

# --- narrate_gm_intervention function remains the same ---
def narrate_gm_intervention(
    player_id: str,
    action_type: str,
    failure_type: str,
    raw_output: Optional[str] = None
    ) -> str:
    # ... (Keep existing implementation, including 'clarification_failed' type if wanted, though less likely now) ...
    # Maybe simplify narration if clarification is removed? Or keep it for other potential future recovery failures.
    # For now, keep as is.
    intervention_prefix = "[bold magenta]GM:[/bold magenta]"
    context = f"observing Player {player_id}'s attempt to {action_type}"

    if failure_type == 'parsing_failed':
        reason_phrases = [
            # Adjust phrasing slightly now GM tries to interpret first
            f"{context}, finds their response confusing or ambiguous.",
            f"{context}, cannot decipher a clear action from their words.",
            f"{context}, sees they provided an unclear choice.",
        ]
        chosen_reason = random.choice(reason_phrases)
        if raw_output and logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(f"GM Intervention Details: Raw output for {player_id} ({action_type}): '{raw_output}'")
        # Consequence if GM *cannot* interpret
        consequence_phrases = [
             "As a result, their action this time has no effect.",
             "Therefore, their turn passes without a specific action being registered.",
             "Regrettably, their intended action could not be determined and fails.",
        ]
    elif failure_type == 'llm_call_failed':
         reason_phrases = [
             f"{context}, senses a moment of profound silence or disconnection.",
             f"{context}, perceives that the player is unresponsive.",
             f"{context}, notes an unexpected absence of thought or action.",
         ]
         chosen_reason = random.choice(reason_phrases)
         consequence_phrases = [
              "Their turn is skipped due to this unresponsiveness.",
              "No action is taken by them this round.",
              "The moment passes, and their opportunity for action is lost.",
         ]
    # Clarification failed is less likely now, but keep for robustness maybe?
    elif failure_type == 'clarification_failed': # Or maybe 'interpretation_failed'?
         reason_phrases = [
             f"after reviewing Player {player_id}'s unclear {action_type} response",
             f"despite trying to interpret Player {player_id}'s {action_type} choice",
         ]
         chosen_reason = random.choice(reason_phrases)
         consequence_phrases = [
              "a clear intention could not be reliably determined. The action fails.",
              "a valid choice could not be extracted. Their turn concludes without action.",
         ]
    else: # Generic fallback
        chosen_reason = f"{context}, encounters an unexpected issue ({failure_type})."
        consequence_phrases = [
            "Their action cannot proceed as intended.",
            "Their turn concludes without a valid action.",
        ]

    chosen_consequence = random.choice(consequence_phrases)
    narrative = f"{intervention_prefix} {chosen_reason} {chosen_consequence}"
    return narrative


# --- MODIFIED GM Handler (Simpler Recovery Logic) ---
# --- Changed back to SYNC function ---
def handle_agent_decision_failure(
    state: GraphState,
    player_id: str,
    failure_details: Dict[str, Any]
    ) -> Dict[str, Any]: # Still returns dict indicating outcome
    """
    Handles agent decision failures. Logs, narrates. Attempts to INTERPRET
    ambiguous key-based parsing failures directly, rather than re-prompting.

    Returns:
        Dict: Contains status ('final_failure' or 'recovered') and,
              if recovered, the 'recovered_key'. Includes updated logs
              and potentially updated 'pending_night_results'.
    """
    status = failure_details.get('status', 'unknown_failure')
    intended_action = failure_details.get('intended_action', 'unknown')
    raw_output = failure_details.get('raw_output', '')
    cleaned_output_for_extraction = failure_details.get('cleaned_output', raw_output or '')
    options = failure_details.get('options') # Dict[str, str]
    current_log = state.get('public_log', [])
    gm_logs_added = []

    # --- Log Initial Failure ---
    # ... (Keep initial logging as before) ...
    logging.error(f"--- GM Handling Failure (Initial) ---")
    logging.error(f"Player: {player_id}")
    logging.error(f"Action Type: {intended_action}")
    logging.error(f"Failure Status: {status}")
    logging.error(f"Failure Details Dict: {failure_details}")
    if raw_output is not None: logging.error(f"Raw LLM Output: '{raw_output}'")
    logging.error(f"--- End GM Handling Failure Log (Initial) ---")


    # --- Attempt Interpretation for Key-Based Parsing Failures ---
    can_interpret = (
        status in ['parsing_failed', 'validation_error_post_success'] and # Include validation errors if needed
        intended_action in ['vote', 'imp_kill', 'investigate'] and
        options is not None and
        cleaned_output_for_extraction # Need some output to interpret
    )

    recovered_key: Optional[str] = None
    final_status = "final_failure" # Default outcome

    if can_interpret:
        logging.info(f"GM attempting to interpret ambiguous response for {player_id}'s {intended_action}...")
        potential_key = None
        # Try extracting the first valid key found in the ambiguous string
        potential_keys_pattern = r'\b(' + '|'.join(re.escape(k) for k in options.keys()) + r')\b'
        match = re.search(potential_keys_pattern, cleaned_output_for_extraction)
        if match:
            potential_key = match.group(1)
            logging.info(f"  GM Interpretation: Extracted potential key '{potential_key}' from output: '{cleaned_output_for_extraction}'")
            # --- Directly Recover Based on Interpretation ---
            recovered_key = potential_key
            final_status = "recovered"
            gm_log_success = f"GM: Interpreted {player_id}'s ambiguous {intended_action} response as Key {recovered_key}. Action recovered."
            gm_logs_added.append(gm_log_success)
            console.print(f"[dim magenta]GM interpreted {player_id}'s choice for {intended_action}.[/dim magenta]") # Subtle confirmation
            # ---------------------------------------------
        else:
            # Interpretation failed, couldn't find a valid key pattern
            logging.warning(f"  GM Interpretation failed: No valid key pattern found in output: '{cleaned_output_for_extraction}'")
            # final_status remains 'final_failure'

    # --- If Interpretation wasn't possible or failed ---
    if final_status == "final_failure":
        # Determine the failure type for narration
        # If interpretation was attempted but failed, maybe use 'interpretation_failed'?
        narrative_failure_type = 'interpretation_failed' if can_interpret else status
        # Narrate final failure
        failure_narrative = narrate_gm_intervention(
            player_id=player_id,
            action_type=intended_action,
            failure_type=narrative_failure_type, # Use appropriate type
            raw_output=raw_output # Show original output
        )
        console.print(failure_narrative)
        gm_log_narrate_fail = f"GM: Player {player_id}'s {intended_action} action ultimately failed ({narrative_failure_type})."
        # Avoid duplicate logging
        if not any(gm_log_narrate_fail in log for log in gm_logs_added):
             gm_logs_added.append(gm_log_narrate_fail)

        # Apply final failure state updates (e.g., for investigation)
        if intended_action == 'investigate':
            investigation_result_str = "You did not receive an investigation result this night due to an unclear choice." # Simplified message
            logging.info(f"GM Final Fallback for {player_id} (investigate): Storing failure message.")
            if 'pending_night_results' not in state or state['pending_night_results'] is None: state['pending_night_results'] = {}
            if player_id not in state['pending_night_results']: state['pending_night_results'][player_id] = {}
            state['pending_night_results'][player_id]['investigation'] = investigation_result_str
            # updated_pending_results will be included in the return dict below

    # --- Return the final status dictionary ---
    result_dict: Dict[str, Any] = {
        "status": final_status,
        "player_id": player_id,
        "action_type": intended_action,
        "logs_added": gm_logs_added,
        "recovered_key": recovered_key,
        # Include updated pending results ONLY if failure occurred and it's investigate
        "updated_pending_results": state.get('pending_night_results') if final_status == "final_failure" and intended_action == 'investigate' else None
    }
    return result_dict