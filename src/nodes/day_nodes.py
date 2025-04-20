# src/nodes/day_nodes.py
import asyncio
import logging
import json # To format log entries
from typing import Dict, Any, Optional, Counter as TypingCounter, List, Union
from collections import Counter, deque

# Import state types and validation
from pydantic import ValidationError
from src.state import GraphState, PlayerState, ActionContext

# Import decision handling and utilities
from src.decision_handler import get_decision

# --- ADDED Imports ---
from src.narrator_utils import (
    narrate_day_begins, narrate_death_announcement, narrate_no_death,
    narrate_vote_results, narrate_execution, narrate_no_execution
)
from src.gm_utils import handle_agent_decision_failure # Import the modified handler
from src.ai_schemas import SpeechOutput

try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console() # Fallback

# --- Day Phase Nodes ---

# start_day_announce remains the same...
def start_day_announce(state: GraphState) -> GraphState:
    # ... (Implementation is correct and synchronous) ...
    console.print("\n[dim blue]--- Entering Day Announcement Phase ---[/dim blue]")

    target_id = state.get("target_of_night_action")
    current_players = state.get("players", [])
    updated_players_list = []
    player_killed_id = None
    round_num = state.get('round_number', '?')
    alive_player_ids = list(state.get('alive_players', [])) # Copy to modify

    # --- Process Kill Logic ---
    if target_id:
        logging.info(f"Processing night target: {target_id}")
        found_and_killed = False
        for p_dict in current_players:
            try:
                if isinstance(p_dict, dict):
                     # Validate player data before processing
                     player = PlayerState.model_validate(p_dict)
                     if player.id == target_id and player.status == 'alive':
                         player.status = 'dead' # Update status
                         player_killed_id = player.id # Store the ID
                         logging.info(f"Player {player.id} status updated to dead (killed).")
                         if player.id in alive_player_ids:
                              alive_player_ids.remove(player.id) # Remove from alive list
                         found_and_killed = True
                     updated_players_list.append(player.model_dump()) # Add updated or original player dict
                else:
                     # Keep non-dict data if it exists, but log warning
                     logging.warning(f"Skipping non-dict player data in start_day_announce processing: {p_dict}")
                     updated_players_list.append(p_dict)
            except ValidationError as e:
                 logging.error(f"Validation Error processing player {p_dict.get('id', 'N/A') if isinstance(p_dict, dict) else 'N/A'} during kill: {e}")
                 # Keep original dict if validation fails but it was a dict
                 if isinstance(p_dict, dict): updated_players_list.append(p_dict)
            except Exception as e:
                 logging.error(f"Unexpected Error processing player {p_dict.get('id', 'N/A') if isinstance(p_dict, dict) else 'N/A'} during kill: {e}", exc_info=True)
                 if isinstance(p_dict, dict): updated_players_list.append(p_dict)


        if not found_and_killed:
             logging.warning(f"Night target {target_id} was not found among alive players or already dead.")
             # If target not found, ensure player list wasn't partially updated
             if not updated_players_list: # If loop didn't run or failed entirely
                 updated_players_list = list(current_players) # Revert to original

        state["players"] = updated_players_list
        state["alive_players"] = alive_player_ids # Use the potentially modified list

    else:
        logging.info("No night target specified in 'target_of_night_action'.")
        state["players"] = current_players # Ensure players list is passed through
        state["alive_players"] = alive_player_ids # Pass original list if no target
    # ---------------------------------------------

    # Set 'last_victim' state field
    state['last_victim'] = player_killed_id
    logging.info(f"Set 'last_victim' state to: {state['last_victim']}")
    state['target_of_night_action'] = None # Clear processed target
    logging.info("Cleared 'target_of_night_action' state.")

    # --- Generate Announcement using Narrator ---
    day_begins_narrative = narrate_day_begins(round_num)
    console.print(day_begins_narrative)

    log_entry_content = "" # For logging later
    if player_killed_id:
        death_narrative = narrate_death_announcement(player_killed_id)
        console.print(death_narrative)
        log_entry_content = f"Player {player_killed_id} was found dead."
    else:
        no_death_narrative = narrate_no_death()
        console.print(no_death_narrative)
        log_entry_content = "No deaths reported overnight."

    # --- Log Entry ---
    log_entry = f"NARRATOR: Day {round_num}. {log_entry_content}"
    # ------------------------

    # Update other state fields
    state["current_phase"] = "Discussion" # Transition to next phase
    if 'public_log' not in state or state['public_log'] is None: state['public_log'] = []
    state['public_log'].append(log_entry) # Append the new log entry

    logging.info("start_day_announce complete using narrator.")
    return state


# --- SYNC discussion_phase, wraps async calls ---
def discussion_phase(state: GraphState) -> GraphState:
    """
    Handles the discussion phase (Sync). Players speak in turns (round-robin).
    AI players return SpeechOutput JSON. Handles failures via GM.
    Returns the full updated state.
    """
    console.print("\n[dim blue]--- Entering Discussion Phase ---[/dim blue]")
    round_num = state.get('round_number', '?')
    alive_player_ids = state.get('alive_players', [])
    current_log_snapshot = state.get('public_log', [])
    discussion_logs_this_phase = []

    player_objects: Dict[str, PlayerState] = {}
    for p_dict in state.get('players', []):
        # ... (validation logic remains the same) ...
        if isinstance(p_dict, dict) and 'id' in p_dict and p_dict['id'] in alive_player_ids:
            try:
                player_objects[p_dict['id']] = PlayerState.model_validate(p_dict)
            except ValidationError as e:
                 logging.warning(f"Skipping invalid alive player data in discussion_phase setup: {p_dict} - Error: {e}")
        elif isinstance(p_dict, dict) and p_dict.get('status') == 'dead': pass
        else: logging.warning(f"Skipping invalid player entry in discussion_phase setup: {p_dict}")

    speaker_queue = deque(list(alive_player_ids))
    MAX_SPEAKING_ROUNDS = 2
    turns_taken_this_phase = 0
    speeches_made_by_player: Dict[str, int] = Counter()

    log_entry_start = f"SYS: Day {round_num}: Discussion begins."
    discussion_logs_this_phase.append(log_entry_start)
    console.print(f"[italic grey50]{log_entry_start.replace('SYS: ', '')}[/italic grey50]")

    while speaker_queue and speeches_made_by_player[speaker_queue[0]] < MAX_SPEAKING_ROUNDS:
        current_player_id = speaker_queue.popleft()
        player = player_objects.get(current_player_id)

        if not player:
             logging.error(f"CRITICAL: Could not find player object for speaker ID: {current_player_id}. Skipping turn.")
             continue

        logging.info(f"Discussion Turn: {current_player_id} (Round {speeches_made_by_player[current_player_id] + 1}/{MAX_SPEAKING_ROUNDS})")

        action_context: ActionContext = {
            "action_type": 'speak', "player_id": current_player_id,
            "is_human": player.is_human, "options": None,
            "prompt_message": f"{current_player_id}, it's your turn to speak. Consider the discussion so far.",
            "full_game_state": {**state, "public_log": current_log_snapshot + discussion_logs_this_phase},
            "player_role": player.role
        }

        decision_result: Union[Optional[Dict], Dict] = None # Expect dict (speech or failure)
        try:
            decision_result = asyncio.run(get_decision(action_context)) # Wrap async call
        except Exception as e:
            logging.error(f"Unexpected Error calling get_decision in discussion_phase for {current_player_id}: {e}", exc_info=True)
            decision_result = {
                 'status': 'exception', 'raw_output': None, 'intended_action': 'speak',
                 'options': None, 'player_id': current_player_id, 'error': str(e)
             }

        if isinstance(decision_result, dict) and 'status' in decision_result:
            logging.warning(f"Decision failure detected for {current_player_id} (speak). Handing off to GM.")
            try:
                # Wrap async GM handler call
                gm_result = asyncio.run(handle_agent_decision_failure(
                    {**state, "public_log": current_log_snapshot + discussion_logs_this_phase},
                    current_player_id,
                    decision_result
                ))
                # Process GM result dictionary
                discussion_logs_this_phase.extend(gm_result.get("logs_added", []))
                # No specific state recovery needed for failed 'speak' beyond GM narration/logs
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler in discussion_phase: {e}", exc_info=True)
                 discussion_logs_this_phase.append(f"SYS: Error during GM handling for {current_player_id}. Turn skipped.")

        elif isinstance(decision_result, dict) and 'speech_content' in decision_result:
            try:
                speech_output = SpeechOutput.model_validate(decision_result)
                speech_content = speech_output.speech_content.strip()

                if not speech_content:
                     logging.warning(f"Player {current_player_id} returned valid JSON but with empty speech_content. Treating as silent.")
                     log_entry = f"{current_player_id} remains silent."
                     discussion_logs_this_phase.append(log_entry)
                     console.print(f"[dim {'green' if player.is_human else 'cyan'}]{current_player_id}[/dim {'green' if player.is_human else 'cyan'}] remains silent.")
                else:
                     log_entry = f"{current_player_id}: {speech_output.model_dump_json()}" # Log full JSON
                     discussion_logs_this_phase.append(log_entry)

                     intent_str = f" (Intent: {speech_output.intent}"
                     if speech_output.target_player: intent_str += f", Target: {speech_output.target_player}"
                     intent_str += ")"
                     color = "green" if player.is_human else "cyan"
                     console.print(f"[{color}]{current_player_id}[/{color}]: \"{speech_content}\"[dim]{intent_str}[/dim]")

            except ValidationError as e:
                 logging.error(f"Validation Error processing successful decision result for {current_player_id}: {e}. Raw dict: {decision_result}")
                 # Treat as failure -> call GM handler
                 failure_dict = {
                     'status': 'validation_error_post_success', 'raw_output': str(decision_result),
                     'intended_action': 'speak', 'options': None, 'player_id': current_player_id,
                     'error': str(e)
                 }
                 try:
                     gm_result = asyncio.run(handle_agent_decision_failure(
                         {**state, "public_log": current_log_snapshot + discussion_logs_this_phase},
                         current_player_id,
                         failure_dict
                     ))
                     discussion_logs_this_phase.extend(gm_result.get("logs_added", []))
                 except Exception as ge:
                    logging.error(f"Error calling/processing GM handler after validation error: {ge}", exc_info=True)
                    discussion_logs_this_phase.append(f"SYS: Error during GM handling for {current_player_id}. Turn skipped.")


        else: # Handle unexpected None or other non-dict results
            logging.info(f"Player {current_player_id} provided no speech output or cancelled.")
            log_entry = f"{current_player_id} remains silent."
            discussion_logs_this_phase.append(log_entry)
            color = "green" if player.is_human else "cyan"
            console.print(f"[dim {color}]{current_player_id}[/dim {color}] remains silent.")

        speeches_made_by_player[current_player_id] += 1
        turns_taken_this_phase += 1
        if speeches_made_by_player[current_player_id] < MAX_SPEAKING_ROUNDS:
            speaker_queue.append(current_player_id)

        # --- Placeholder for GM Checkpoint ---
        # ... (keep placeholder) ...

    log_entry_end = f"SYS: Discussion concluded (Round {round_num})."
    discussion_logs_this_phase.append(log_entry_end)
    console.print(f"[italic grey50]{log_entry_end.replace('SYS: ', '')}[/italic grey50]")

    state["public_log"] = current_log_snapshot + discussion_logs_this_phase
    state["current_phase"] = "Voting"

    logging.info(f"discussion_phase complete. {turns_taken_this_phase} turns taken.")
    return state


# --- SYNC voting_phase, wraps async calls ---
def voting_phase(state: GraphState) -> GraphState:
    """
    Each alive player attempts to vote (Sync), GM handles failures potentially with
    interactive clarification. Returns the full updated state.
    """
    console.print("\n[dim blue]--- Entering Voting Phase ---[/dim blue]")
    alive_player_ids = state.get('alive_players', [])
    current_log = state.get('public_log', [])
    logs_added_this_node = []
    player_objects = {}
    for p_dict in state.get('players', []):
        # ... (validation logic remains the same) ...
        if isinstance(p_dict, dict) and 'id' in p_dict:
            try:
                player_objects[p_dict['id']] = PlayerState.model_validate(p_dict)
            except ValidationError as e:
                 logging.warning(f"Skipping invalid player data in voting_phase setup: {p_dict} - Error: {e}")
        else:
             logging.warning(f"Skipping invalid player entry in voting_phase setup: {p_dict}")


    log_entry_start = f"SYS: Day {state.get('round_number', '?')}: Voting begins. Votes are cast privately."
    logs_added_this_node.append(log_entry_start)
    console.print(f"[italic grey50]{log_entry_start.replace('SYS: ', '')}[/italic grey50]")

    votes_cast: Dict[str, str] = {}

    for player_id in alive_player_ids:
        player = player_objects.get(player_id)
        if not player:
             logging.warning(f"Could not find validated player object for alive ID during voting: {player_id}")
             logs_added_this_node.append(f"SYS: Skipping vote for {player_id} (data error).")
             continue

        vote_options_list = [p_id for p_id in alive_player_ids if p_id != player_id]
        if not vote_options_list:
             abstain_log = f"VOTE: {player_id} abstains (no valid targets)."
             logs_added_this_node.append(abstain_log)
             console.print(f"[dim {'green' if player.is_human else 'cyan'}]{player_id}[/dim {'green' if player.is_human else 'cyan'}] abstains (no targets).")
             continue

        options_dict = {str(i+1): target_player_id for i, target_player_id in enumerate(vote_options_list)}
        prompt_lines = [f"{player_id}, choose who to vote for execution:"]
        prompt_lines.extend([f"  {k}: {v}" for k, v in options_dict.items()])
        prompt_lines.append(f"**IMPORTANT: Reply ONLY with the numerical key (1-{len(options_dict)}) corresponding to your choice.**")
        prompt_msg = "\n".join(prompt_lines)

        action_context: ActionContext = {
            "action_type": 'vote', "player_id": player_id,
            "is_human": player.is_human, "options": options_dict,
            "prompt_message": prompt_msg,
            "full_game_state": {**state, "public_log": current_log + logs_added_this_node},
            "player_role": player.role
        }

        decision_result: Union[Optional[str], Dict] = None
        try:
            decision_result = asyncio.run(get_decision(action_context)) # Wrap async call
        except Exception as e:
            logging.error(f"Unexpected Error calling get_decision in voting_phase for {player_id}: {e}", exc_info=True)
            decision_result = {
                 'status': 'exception', 'raw_output': None, 'intended_action': 'vote',
                 'options': options_dict, 'player_id': player_id, 'error': str(e)
             }

        color = "green" if player.is_human else "cyan"
        final_key: Optional[str] = None

        if isinstance(decision_result, dict) and 'status' in decision_result:
            logging.warning(f"Decision failure detected for {player_id} (vote). Handing off to GM.")
            try:
                gm_result = asyncio.run(handle_agent_decision_failure( # Wrap async call
                    {**state, "public_log": current_log + logs_added_this_node},
                    player_id,
                    decision_result
                ))
                logs_added_this_node.extend(gm_result.get("logs_added", []))
                if gm_result.get("status") == "recovered":
                     final_key = gm_result.get("recovered_key")
                     logging.info(f"GM recovery successful for {player_id} (vote). Using recovered key: {final_key}")
                else:
                     logging.info(f"GM handling resulted in final failure for {player_id} (vote).")
                     final_key = None
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler in voting_phase: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {player_id}. Vote abstained.")
                 final_key = None

        elif decision_result and isinstance(decision_result, str) and decision_result in options_dict:
            final_key = decision_result
            logging.info(f"{player_id} voted successfully (Key: {final_key}).")

        else: # Handle invalid direct input
            logging.warning(f"{player_id} (vote) resulted in invalid input ({decision_result}). Treating as failure.")
            invalid_input_failure = {
                'status': 'parsing_failed', 'raw_output': str(decision_result), 'cleaned_output': str(decision_result),
                'intended_action': 'vote', 'options': options_dict, 'player_id': player_id,
                'error_details': 'Invalid key or None received directly.'
            }
            try:
                gm_result = asyncio.run(handle_agent_decision_failure( # Wrap async call
                    {**state, "public_log": current_log + logs_added_this_node},
                    player_id,
                    invalid_input_failure
                ))
                logs_added_this_node.extend(gm_result.get("logs_added", []))
                if gm_result.get("status") == "recovered":
                    final_key = gm_result.get("recovered_key")
                else:
                    final_key = None
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler for invalid input in voting_phase: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {player_id}. Vote abstained.")
                 final_key = None

        # --- Record Vote or Log Abstention ---
        if final_key and final_key in options_dict:
             target_id = options_dict[final_key]
             votes_cast[player_id] = target_id
             log_entry = f"VOTE: {player_id} has cast their vote."
             logs_added_this_node.append(log_entry)
             console.print(f"[dim {color}]{player_id}[/dim {color}] voted.")
             logging.info(f"{player_id} final vote for {target_id} (Key: {final_key}) - Secret until tally.")
        else:
             log_entry = f"VOTE: {player_id} abstained."
             # Avoid redundant log if GM already explained failure
             if not any("action ultimately failed" in log for log in logs_added_this_node[-3:] if log.startswith(f"GM:")) :
                 logs_added_this_node.append(log_entry)
             console.print(f"[dim {color}]{player_id}[/dim {color}] abstained.")

    log_entry_end = "SYS: Voting concluded."
    logs_added_this_node.append(log_entry_end)
    console.print(f"[italic grey50]{log_entry_end.replace('SYS: ', '')}[/italic grey50]")

    state["votes"] = votes_cast
    state["public_log"] = current_log + logs_added_this_node
    state["current_phase"] = "Tallying"

    logging.info("voting_phase complete.")
    return state

# --- tally_votes, announce_process_execution, announce_no_execution remain synchronous ---
# ... (Keep existing synchronous implementations for these) ...
def tally_votes(state: GraphState) -> GraphState:
    # ... (No changes needed) ...
    console.print("\n[dim blue]--- Entering Vote Tally Phase ---[/dim blue]")
    votes_cast = state.get('votes', {}) # Reads votes collected in previous step
    current_log = state.get('public_log', [])
    tally_logs = [] # Collect logs for this phase

    execution_target_id: Optional[str] = None
    tied_players: List[str] = []
    vote_counts: TypingCounter[str] = Counter()

    state['previous_round_votes'] = votes_cast.copy() # Store for context
    logging.info(f"Stored previous round votes: {state['previous_round_votes']}")

    # --- Tally Logic (Internal) ---
    if votes_cast:
        # Count votes for each target
        for voter, target in votes_cast.items():
             if target: # Ensure target is not None or empty
                 vote_counts[target] += 1
                 # Log individual vote reveal for debugging/transparency
                 reveal_log = f"VOTE_REVEAL: {voter} voted for {target}"
                 tally_logs.append(reveal_log)

        # Determine outcome based on counts
        if vote_counts:
            max_votes = vote_counts.most_common(1)[0][1]
            # --- Ensure majority is met (more than half of voters, or highest if no majority possible?) ---
            # Simple majority: requires > len(alive_players) / 2
            # Or highest count wins? Let's stick to highest count for now, handle ties.
            # num_voters = len(votes_cast) # Number of people who actually voted
            num_alive = len(state.get('alive_players',[])) # Base on total alive for potential majority rules
            required_for_majority = (num_alive // 2) + 1
            logging.debug(f"Vote Tally: Counts={vote_counts}, MaxVotes={max_votes}, RequiredForMajority={required_for_majority}")

            if max_votes > 0: # Ensure there was at least one vote cast for someone
                 candidates = [p for p, c in vote_counts.items() if c == max_votes]
                 # --- Check for Tie OR Single Highest ---
                 if len(candidates) == 1:
                     # Check if the single highest meets majority threshold (optional rule)
                     # if max_votes >= required_for_majority:
                     #     execution_target_id = candidates[0]
                     # else:
                     #     logging.info(f"Highest vote count ({max_votes}) for {candidates[0]} did not meet majority ({required_for_majority}). No execution.")
                     # For now, highest count wins regardless of majority:
                     execution_target_id = candidates[0] # Single target with most votes
                     logging.info(f"Execution target determined: {execution_target_id} with {max_votes} votes.")
                 elif len(candidates) > 1:
                     tied_players = sorted(candidates) # Multiple targets tied for most votes
                     logging.info(f"Tie detected between {tied_players} with {max_votes} votes each. No execution.")
                 # else case (max_votes > 0 but len(candidates) == 0) is logically impossible
            else:
                 logging.info("Votes were cast, but all were invalid or target counts were zero?") # Should be rare
        else:
             logging.info("Votes dictionary exists, but no valid targets received votes.") # e.g., { 'Alice': None }
    else:
        logging.info("No votes were cast in this round.")
    # --- End Tally Logic ---

    # --- Announce Results using Narrator ---
    narrative_text = narrate_vote_results(
        vote_counts=vote_counts,
        execution_target=execution_target_id,
        tied_players=tied_players if tied_players else None
    )
    console.print(narrative_text)

    # Add a summary log entry based on outcome
    outcome_summary = "No votes cast."
    if execution_target_id: outcome_summary = f"Execution target: {execution_target_id}."
    elif tied_players: outcome_summary = f"Vote tied between {', '.join(tied_players)}."
    elif vote_counts: outcome_summary = "No majority reached (or only invalid votes)." # Refined message
    tally_logs.append(f"NARRATOR: Vote Results - {outcome_summary}")
    # --- End Narrator Announcement ---

    # --- Update State ---
    state["execution_target"] = execution_target_id # This determines the next edge
    state["votes"] = {} # Clear votes map for the next round
    state["public_log"] = current_log + tally_logs # Append tally logs
    state["current_phase"] = "Execution" # Transition phase

    # Set last_executed marker string based on outcome for context/history
    if execution_target_id:
        state["last_executed"] = None # Will be set to player ID by execution node
    elif tied_players:
        state["last_executed"] = "None (Tie)"
    elif not votes_cast or not vote_counts: # Handles no votes or only invalid votes
        state["last_executed"] = "None (No Votes/Majority)"
    else: # Catch-all for no execution without tie (e.g. multiple ppl got 1 vote each, less than majority?) - refine if needed
        state["last_executed"] = "None (No Majority)"

    logging.info(f"tally_votes complete. execution_target set to: {execution_target_id}. last_executed marker set to: {state['last_executed']}")
    return state


def announce_process_execution(state: GraphState) -> GraphState:
    # ... (No changes needed) ...
    console.print("\n[dim blue]--- Entering Execution Phase (Processing) ---[/dim blue]")
    target_id = state.get("execution_target") # Read target from state
    current_players = state.get("players", [])
    updated_players_list = []
    player_executed_id = None
    alive_player_ids = list(state.get('alive_players', [])) # Copy to modify

    if not target_id:
         # Should not happen due to graph logic, but handle defensively
         logging.error("announce_process_execution node reached unexpectedly without target_id")
         log_message = f"SYS: Day {state.get('round_number', '?')}: ERROR - Execution node reached without target."
         console.print("[bold red]Error: Execution node reached without a target![/bold red]")
         state["last_executed"] = "Error" # Set error state
         state["public_log"] = state.get("public_log", []) + [log_message]
         return state

    # --- Announce Execution using Narrator ---
    narrative_text = narrate_execution(target_id)
    console.print(narrative_text)
    # --- End Narrator Announcement ---

    # --- Process Execution Logic (Internal) ---
    logging.info(f"Processing execution for target: {target_id}")
    found_and_executed = False
    for p_dict in current_players:
        try:
             if isinstance(p_dict, dict):
                player = PlayerState.model_validate(p_dict)
                if player.id == target_id and player.status == 'alive':
                    player.status = 'dead' # Update status
                    player_executed_id = player.id # Store the actual executed ID
                    logging.info(f"Player {player.id} status updated to dead (executed).")
                    if player.id in alive_player_ids:
                        alive_player_ids.remove(player.id) # Remove from alive list
                    found_and_executed = True
                # Append regardless of modification status
                updated_players_list.append(player.model_dump())
             else:
                  logging.warning(f"Skipping non-dict player data in announce_process_execution: {p_dict}")
                  updated_players_list.append(p_dict) # Keep non-dict data
        except ValidationError as e:
             logging.error(f"Validation Error processing player {p_dict.get('id', 'N/A') if isinstance(p_dict, dict) else 'N/A'} during execution: {e}")
             if isinstance(p_dict, dict): updated_players_list.append(p_dict) # Keep original dict
        except Exception as e:
            logging.error(f"Unexpected Error processing player {p_dict.get('id', 'N/A') if isinstance(p_dict, dict) else 'N/A'} during execution: {e}", exc_info=True)
            if isinstance(p_dict, dict): updated_players_list.append(p_dict)
    # --- End Processing Logic ---

    state["players"] = updated_players_list
    state["alive_players"] = alive_player_ids

    # --- Set State and Log ---
    log_entry = ""
    if found_and_executed and player_executed_id:
        state["last_executed"] = player_executed_id # Store the actual executed player ID
        log_entry = f"NARRATOR: Player {player_executed_id} was executed by vote."
        logging.info(f"Set 'last_executed' state to: {player_executed_id}")
    else:
        # Execution target was set, but player wasn't found/alive - reflects inconsistency
        state["last_executed"] = f"Failed Target ({target_id})" # Indicate failed attempt
        log_entry = f"SYS: Attempted execution of {target_id} failed (player not found or already dead)."
        console.print(f"[dim yellow]WARN: Attempted to execute {target_id}, but they could not be processed.[/dim yellow]")
        logging.warning(f"Attempted to execute {target_id}, but processing failed.")

    state["execution_target"] = None # Clear the execution target for next round
    state["public_log"] = state.get("public_log", []) + [log_entry]
    # Phase will be updated by conditional edge logic after check_game_over_final

    logging.info("announce_process_execution complete.")
    return state


def announce_no_execution(state: GraphState) -> GraphState:
    # ... (No changes needed) ...
    console.print("\n[dim blue]--- Entering Execution Phase (No Execution) ---[/dim blue]")

    # Read the reason marker set in tally_votes
    no_execution_marker = state.get("last_executed", "None (Unknown Reason)")
    reason = "Unknown Reason" # Default
    # Parse the reason from the marker string
    if isinstance(no_execution_marker, str):
        if "Tie" in no_execution_marker: reason = "Tie"
        elif "No Votes" in no_execution_marker: reason = "No Votes/Majority"
        elif "No Majority" in no_execution_marker: reason = "No Majority"
        # Add more specific reasons if tally_votes sets them

    # The main announcement happened via narrate_vote_results in tally_votes.
    # This node logs confirmation and ensures state consistency.

    log_message = f"NARRATOR: No execution occurred due to {reason.lower()}."
    logging.info(f"Confirmed no execution due to {reason}. 'last_executed' remains '{no_execution_marker}'.")

    # Optional: Use narrate_no_execution for extra emphasis if needed, but might be redundant.
    # narrative_text = narrate_no_execution(reason)
    # console.print(narrative_text)

    # --- Final State Updates ---
    state["execution_target"] = None # Ensure target is None
    state["public_log"] = state.get("public_log", []) + [log_message]
    # Phase will be updated by conditional edge logic

    logging.info("announce_no_execution node confirmed state.")
    return state