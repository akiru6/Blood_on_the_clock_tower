# src/nodes/night_nodes.py
import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, Literal

# Import state types and validation
from pydantic import ValidationError
from src.state import GraphState, PlayerState, ActionContext # Was: from ..state import ...
from src.decision_handler import get_decision             # Was: from ..decision_handler import ...
from src.utils import get_actor_and_targets               # Was: from ..utils import ...
from src.narrator_utils import narrate_night_begins       # Was: from ..narrator_utils import ...
from src.gm_utils import handle_agent_decision_failure    # Was: from ..gm_utils 

try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console()

# --- Night Phase Nodes ---

def start_night_phase(state: GraphState) -> GraphState:
    """Node for the start of the Night phase. Clears pending results. Returns the full updated state."""
    round_num_display = state.get('round_number', 0) + 1
    new_round_number = round_num_display

    narrative_text = narrate_night_begins(new_round_number)
    console.print(narrative_text)

    state['current_phase'] = "Night"
    state['round_number'] = new_round_number
    state['last_victim'] = None # Reset last victim for the new night
    state['pending_night_results'] = {} # Clear pending results
    logging.info("Cleared pending_night_results for the new night.")

    if 'public_log' not in state or state['public_log'] is None:
        state['public_log'] = []

    log_entry = f"SYS: Round {new_round_number}: Night phase begins."
    state['public_log'].append(log_entry)

    logging.info(f"Updating phase to Night, Round to {new_round_number}. Reset last_victim and pending_night_results.")
    return state


# --- SYNC imp_action, wraps async calls ---
def imp_action(state: GraphState) -> GraphState:
    """
    Impostor action node (Sync). Attempts get target, handles failure via GM
    (potentially with interactive clarification), sets 'target_of_night_action'
    on success or recovery. Returns the full updated state.
    """
    console.print("[dim blue]--- Entering Impostor Action Phase ---[/dim blue]")
    imp_player_obj: Optional[PlayerState]
    potential_targets_objs: List[PlayerState]
    imp_player_obj, potential_targets_objs = get_actor_and_targets(state, 'Imp')

    target_id: Optional[str] = None
    state['target_of_night_action'] = None
    current_log = state.get('public_log', [])
    logs_added_this_node = []
    round_num = state.get('round_number', '?')
    player_id_for_log = "Impostor (Unknown)" # Default

    if not imp_player_obj:
        log_message = f"SYS: Night {round_num}: Error - No alive Impostor for action."
        console.print(f"[dim yellow]{log_message}[/dim yellow]")
        logs_added_this_node.append(log_message)
    elif not potential_targets_objs:
        player_id_for_log = imp_player_obj.id
        log_message = f"SYS: Night {round_num}: Impostor ({player_id_for_log}) finds no valid targets."
        console.print(f"[dim yellow]{log_message}[/dim yellow]")
        logs_added_this_node.append(log_message)
    else:
        player_id_for_log = imp_player_obj.id
        options_dict = {str(i+1): p.id for i, p in enumerate(potential_targets_objs)}
        prompt_lines = [f"Impostor '{imp_player_obj.id}', choose target to eliminate:"]
        prompt_lines.extend([f"  {k}: {v}" for k, v in options_dict.items()])
        prompt_lines.append(f"**IMPORTANT: Reply ONLY with the numerical key (1-{len(options_dict)}) corresponding to your target.**")
        prompt_msg = "\n".join(prompt_lines)

        action_context: ActionContext = {
            "action_type": 'imp_kill', "player_id": imp_player_obj.id,
            "is_human": imp_player_obj.is_human, "options": options_dict,
            "prompt_message": prompt_msg,
            "full_game_state": {**state, "public_log": current_log + logs_added_this_node},
            "player_role": imp_player_obj.role
        }

        decision_result: Union[Optional[str], Dict] = None
        try:
            decision_result = asyncio.run(get_decision(action_context))
        except Exception as e:
             logging.error(f"Unexpected Error calling get_decision in imp_action: {e}", exc_info=True)
             decision_result = {
                 'status': 'exception', 'raw_output': None, 'intended_action': 'imp_kill',
                 'options': options_dict, 'player_id': imp_player_obj.id, 'error': str(e)
             }

        final_key: Optional[str] = None
        if isinstance(decision_result, dict) and 'status' in decision_result:
            logging.warning(f"Decision failure detected for Impostor {imp_player_obj.id}. Handing off to GM.")
            try:
                gm_result = asyncio.run(handle_agent_decision_failure(
                    {**state, "public_log": current_log + logs_added_this_node},
                    imp_player_obj.id,
                    decision_result
                ))
                logs_added_this_node.extend(gm_result.get("logs_added", []))
                if gm_result.get("status") == "recovered":
                     final_key = gm_result.get("recovered_key")
                     logging.info(f"GM recovery successful for {imp_player_obj.id}. Using recovered key: {final_key}")
                else:
                     logging.info(f"GM handling resulted in final failure for {imp_player_obj.id}.")
                     final_key = None # Ensure key is None on final failure
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler in imp_action: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {imp_player_obj.id}. Action fails.")
                 final_key = None

        elif decision_result and isinstance(decision_result, str) and decision_result in options_dict:
             final_key = decision_result
             logging.info(f"Imp {imp_player_obj.id} chose target (Key: {final_key}).")

        else: # Handle invalid direct input
            logging.warning(f"Impostor {imp_player_obj.id} action resulted in invalid input ({decision_result}). Treating as failure.")
            invalid_input_failure = {
                'status': 'parsing_failed', 'raw_output': str(decision_result), 'cleaned_output': str(decision_result),
                'intended_action': 'imp_kill', 'options': options_dict, 'player_id': imp_player_obj.id,
                'error_details': 'Invalid key or None received directly.'
            }
            try:
                gm_result = asyncio.run(handle_agent_decision_failure(
                    {**state, "public_log": current_log + logs_added_this_node},
                    imp_player_obj.id,
                    invalid_input_failure
                ))
                logs_added_this_node.extend(gm_result.get("logs_added", []))
                if gm_result.get("status") == "recovered":
                    final_key = gm_result.get("recovered_key")
                else:
                    final_key = None
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler for invalid input in imp_action: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {imp_player_obj.id}. Action fails.")
                 final_key = None

        # --- Apply Final Result ---
        if final_key and final_key in options_dict:
             target_id = options_dict[final_key]
             state['target_of_night_action'] = target_id
             log_message = f"SYS: Night {round_num}: A shadow moves..."
             logs_added_this_node.append(log_message)
             logging.info(f"Final target for {imp_player_obj.id}: {target_id} (Key: {final_key}). Stored in 'target_of_night_action'.")
        else:
             state['target_of_night_action'] = None
             log_message = f"SYS: Night {round_num}: The Impostor's ({player_id_for_log}) action resulted in no target."
             # Check logs added by GM to avoid redundancy
             if not any("action ultimately failed" in log or "intention is unclear" in log or "action cannot proceed" in log for log in logs_added_this_node if log.startswith("GM:")):
                 logs_added_this_node.append(log_message)
             logging.info(f"Impostor {imp_player_obj.id} action ultimately resulted in no target.")

    # Update the main state log
    state['public_log'] = current_log + logs_added_this_node

    logging.info("imp_action complete. 'target_of_night_action' reflects final outcome.")
    return state


# --- SYNC investigator_action, wraps async calls ---
def investigator_action(state: GraphState) -> GraphState:
    """
    Investigator action node (Sync). Attempts get target, handles failure via GM
    (potentially with interactive clarification), stores investigation result
    (or failure message) in pending_night_results, and prints result immediately
    for Human Investigator. Returns the full updated state.
    """
    console.print("[dim blue]--- Entering Investigator Action Phase ---[/dim blue]")
    investigator_player_obj: Optional[PlayerState]
    potential_targets_objs: List[PlayerState]
    investigator_player_obj, potential_targets_objs = get_actor_and_targets(state, 'Investigator')

    round_num = state.get('round_number', '?')
    current_log = state.get('public_log', [])
    logs_added_this_node = []
    investigation_target_key: Optional[str] = None
    options_dict: Dict[str, str] = {} # Define options_dict early for broader scope

    if not investigator_player_obj:
        logging.info(f"Night {round_num}: No alive Investigator found for action.")
        return state # Return state unmodified if no investigator
    elif not potential_targets_objs:
        investigator_id = investigator_player_obj.id
        log_message = f"SYS: Night {round_num}: Investigator ({investigator_id}) finds no valid targets."
        if investigator_player_obj.is_human:
             console.print(f"[dim yellow]{log_message.replace('SYS: ','')}[/dim yellow]")
        logs_added_this_node.append(log_message)
        # Skip decision logic if no targets
    else:
        investigator_id = investigator_player_obj.id
        options_dict = {str(i+1): p.id for i, p in enumerate(potential_targets_objs)}
        prompt_lines = [f"Investigator '{investigator_id}', choose a player to investigate:"]
        prompt_lines.extend([f"  {k}: {v}" for k, v in options_dict.items()])
        prompt_lines.append(f"**IMPORTANT: Reply ONLY with the numerical key (1-{len(options_dict)}) corresponding to your target.**")
        prompt_msg = "\n".join(prompt_lines)

        action_context: ActionContext = {
            "action_type": 'investigate', "player_id": investigator_id,
            "is_human": investigator_player_obj.is_human, "options": options_dict,
            "prompt_message": prompt_msg,
            "full_game_state": {**state, "public_log": current_log + logs_added_this_node},
            "player_role": investigator_player_obj.role
        }

        decision_result: Union[Optional[str], Dict] = None
        try:
            decision_result = asyncio.run(get_decision(action_context))
        except Exception as e:
            logging.error(f"Unexpected Error calling get_decision in investigator_action for {investigator_id}: {e}", exc_info=True)
            decision_result = {
                 'status': 'exception', 'raw_output': None, 'intended_action': 'investigate',
                 'options': options_dict, 'player_id': investigator_id, 'error': str(e)
             }

        if isinstance(decision_result, dict) and 'status' in decision_result:
            logging.warning(f"Decision failure detected for Investigator {investigator_id}. Handing off to GM.")
            try:
                gm_result = asyncio.run(handle_agent_decision_failure(
                    {**state, "public_log": current_log + logs_added_this_node},
                    investigator_id,
                    decision_result
                ))
                logs_added_this_node.extend(gm_result.get("logs_added", []))
                if gm_result.get("status") == "recovered":
                     investigation_target_key = gm_result.get("recovered_key")
                     logging.info(f"GM recovery successful for {investigator_id}. Using recovered key: {investigation_target_key}")
                else:
                     logging.info(f"GM handling resulted in final failure for {investigator_id}.")
                     investigation_target_key = None
                     if gm_result.get("updated_pending_results") is not None:
                          state['pending_night_results'] = gm_result["updated_pending_results"]
            except Exception as e:
                 logging.error(f"Error calling/processing GM handler in investigator_action: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {investigator_id}. Action fails.")
                 investigation_target_key = None

        elif decision_result and isinstance(decision_result, str) and decision_result in options_dict:
             investigation_target_key = decision_result
             logging.info(f"Investigator {investigator_id} chose target (Key: {investigation_target_key}).")

        else: # Handle invalid direct input
             logging.warning(f"Investigator {investigator_id} action resulted in invalid input ({decision_result}). Treating as failure.")
             invalid_input_failure = {
                'status': 'parsing_failed', 'raw_output': str(decision_result), 'cleaned_output': str(decision_result),
                'intended_action': 'investigate', 'options': options_dict, 'player_id': investigator_id,
                'error_details': 'Invalid key or None received directly.'
             }
             try:
                 gm_result = asyncio.run(handle_agent_decision_failure(
                     {**state, "public_log": current_log + logs_added_this_node},
                     investigator_id,
                     invalid_input_failure
                 ))
                 logs_added_this_node.extend(gm_result.get("logs_added", []))
                 if gm_result.get("status") == "recovered":
                      investigation_target_key = gm_result.get("recovered_key")
                 else:
                      investigation_target_key = None
                      if gm_result.get("updated_pending_results") is not None:
                           state['pending_night_results'] = gm_result["updated_pending_results"]
             except Exception as e:
                 logging.error(f"Error calling/processing GM handler for invalid input in investigator_action: {e}", exc_info=True)
                 logs_added_this_node.append(f"SYS: Error during GM handling for {investigator_id}. Action fails.")
                 investigation_target_key = None

    # --- Determine and Store Investigation Result ---
    investigation_result_str: Optional[str] = None
    # Check if the action succeeded (valid key exists)
    if investigation_target_key and investigation_target_key in options_dict:
        target_id = options_dict[investigation_target_key]
        logging.info(f"Investigator {investigator_id} final target: {target_id}. Determining result.")

        target_role: Optional[Literal['Imp', 'Villager', 'Investigator']] = None
        all_players_dict = {p['id']: p for p in state['players']}
        target_player_dict = all_players_dict.get(target_id)
        temp_result_str = f"Error: Could not find details for target {target_id}."

        if target_player_dict:
              target_role = target_player_dict.get('role')
              alignment = "Evil" if target_role == 'Imp' else "Good"
              temp_result_str = f"Your investigation revealed Player {target_id} is associated with the [bold {'magenta' if alignment == 'Evil' else 'green'}]{alignment}[/bold {'magenta' if alignment == 'Evil' else 'green'}] team."
              logging.info(f"Investigation result for {investigator_id}: Target={target_id}, Role={target_role}, Alignment={alignment}.")
        else:
              logging.error(f"Could not find target player data for ID: {target_id}")

        investigation_result_str = temp_result_str

        # Ensure structure exists and store result
        if 'pending_night_results' not in state or state['pending_night_results'] is None: state['pending_night_results'] = {}
        if investigator_id not in state['pending_night_results']: state['pending_night_results'][investigator_id] = {}
        state['pending_night_results'][investigator_id]['investigation'] = investigation_result_str
        logging.info(f"Stored successful investigation result for {investigator_id} in pending_night_results.")

    # --- Handle Final Failure Case (Ensure message exists) ---
    elif investigator_player_obj: # Check investigator exists before accessing ID
         investigator_id = investigator_player_obj.id
         # Ensure structure exists
         if 'pending_night_results' not in state or state['pending_night_results'] is None: state['pending_night_results'] = {}
         if investigator_id not in state['pending_night_results']: state['pending_night_results'][investigator_id] = {}
         # Only set failure message if GM handler didn't already set one
         if 'investigation' not in state['pending_night_results'][investigator_id]:
             investigation_result_str = "You did not receive an investigation result this night due to unclear instructions or failure to act."
             state['pending_night_results'][investigator_id]['investigation'] = investigation_result_str
             logging.info(f"Stored generic failure message for Investigator {investigator_id} because action failed.")
         else:
             # Retrieve the message already set (likely by GM handler)
             investigation_result_str = state['pending_night_results'][investigator_id]['investigation']

    # --- IMMEDIATE DELIVERY TO HUMAN INVESTIGATOR ---
    if investigator_player_obj and investigator_player_obj.is_human and investigation_result_str is not None:
         console.print(f"\n[bold yellow]GM (Private):[/bold yellow] {investigation_result_str}")
         logging.info(f"Displayed investigation result directly to human investigator {investigator_id}.")

    # Vague public log if action was attempted
    if investigator_player_obj and potential_targets_objs:
        log_message = f"SYS: Night {round_num}: Eyes watch in the darkness..."
        logs_added_this_node.append(log_message)

    # Update the main state log
    state['public_log'] = current_log + logs_added_this_node

    logging.info("investigator_action complete.")
    return state