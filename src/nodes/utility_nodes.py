# src/nodes/utility_nodes.py
import random
from typing import Dict, Any, List, Literal # Added Literal
import logging
from pydantic import ValidationError

# Import the global console
try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console() # Fallback

# Use the updated state definition
from ..state import PlayerState, GraphState

# initialize_game remains the same
def initialize_game(config: Dict[str, Any]) -> GraphState:
    """Helper function to set up the initial game state, including Investigator role."""
    console.print("[dim blue]--- Initializing Game ---[/dim blue]")
    player_ids: List[str] = config.get("player_ids", [])
    human_player_id: str = config.get("human_player_id", "")
    logging.info(f"initialize_game called with config: {config}")

    num_players = len(player_ids)
    if num_players < 3:
        raise ValueError(f"Insufficient players provided for game setup: {player_ids}. Need at least 3.")
    if human_player_id not in player_ids:
         raise ValueError(f"Human player ID '{human_player_id}' not found in player list: {player_ids}")

    # --- Role Counts (Example Logic) ---
    # Needs refinement for different player counts
    imp_count = 1
    investigator_count = 1 if num_players >= 4 else 0
    villager_count = num_players - imp_count - investigator_count

    if villager_count < 1:
         # Adjust logic if needed, maybe prioritize Villager over Investigator if low count?
         investigator_count = 0 # Example adjustment
         villager_count = num_players - imp_count - investigator_count
         if villager_count < 1: # Still an issue
              raise ValueError(f"Cannot assign roles with {num_players} players: results in {villager_count} villagers.")
         logging.warning(f"Adjusted roles for {num_players} players: {imp_count} Imp, {investigator_count} Inv, {villager_count} Villager")
    # --------------------

    available_player_ids = list(player_ids)
    random.shuffle(available_player_ids)

    # --- Assign Roles ---
    impostors = available_player_ids[:imp_count]
    investigators = available_player_ids[imp_count : imp_count + investigator_count]
    # The rest are villagers

    player_states: List[PlayerState] = []
    console.print("[dim]Assigning Roles:[/dim]")
    for p_id in player_ids:
        role: Literal['Imp', 'Villager', 'Investigator'] # Type hint for clarity
        if p_id in impostors:
            role = 'Imp'
        elif p_id in investigators:
            role = 'Investigator'
        else:
            role = 'Villager'

        is_human = (p_id == human_player_id)
        try:
            player_state = PlayerState(id=p_id, role=role, is_human=is_human, status='alive')
            player_states.append(player_state)
            role_display = f"{role}{'(*)' if role != 'Villager' else ''}"
            logging.info(f"  Assigned: ID={p_id}, Role={role_display}, Human={is_human}")
        except ValidationError as e:
            logging.error(f"Failed to create PlayerState for {p_id}: {e}")
            raise ValueError(f"Error creating player state for {p_id}. Check configuration.") from e
    # --------------------

    initial_alive = list(player_ids)
    console.print(f"[dim]Initial Alive Players: {', '.join(initial_alive)}[/dim]")

    # --- Create Initial GraphState Dictionary ---
    initial_graph_state: GraphState = {
        "players": [p.model_dump() for p in player_states],
        "current_phase": "Night", # Start at Night
        "round_number": 0,
        "alive_players": initial_alive,
        "votes": {},
        "execution_target": None,
        "game_over": False,
        "winner": None,
        "public_log": [f"SYS: Game Initialized with players: {', '.join(player_ids)}"],
        "previous_round_votes": {},
        "target_of_night_action": None,
        "last_victim": None,
        "last_executed": None,
        "pending_night_results": {},
    }
    console.print("[dim green]--- Initialization Complete ---[/dim green]")
    return initial_graph_state


# --- Game End Node (MODIFIED) ---
def set_winner_and_end(state: GraphState) -> GraphState: # Return GraphState
    """Determines the winner based on current alive players, reveals roles, and sets game over state."""
    console.print("\n[dim blue]--- Entering Game Over Check ---[/dim blue]")
    # --- Calculate CURRENT alive counts ---
    current_alive_imps = 0 # Renamed to avoid confusion
    current_alive_good = 0 # Renamed for clarity
    # ------------------------------------
    winner = 'Unknown/Draw' # Default
    player_details_list = [] # To store details for reveal

    if 'players' not in state or not state['players']: # Check if players list exists and is not empty
         console.print("[bold red]ERROR: 'players' list missing or empty in state during winner determination.[/bold red]")
         logging.error("State missing or has empty 'players' key in set_winner_and_end.")
         winner = "Error"
    else:
        for p_dict in state.get('players',[]):
            # More robust check before validation
            if not isinstance(p_dict, dict) or not all(k in p_dict for k in ['id', 'role', 'status']):
                 logging.warning(f"Skipping invalid player data during win check: {p_dict}")
                 continue
            try:
                player = PlayerState.model_validate(p_dict) # Validate data structure
                # Store details for final reveal regardless of status
                player_details_list.append({
                    "id": player.id,
                    "role": player.role,
                    "status": player.status
                })
                # Count ALIVE players for win condition check
                if player.status == 'alive':
                    if player.role == 'Imp':
                         current_alive_imps += 1 # Increment current imp count
                    else: # Villager and Investigator are Good
                         current_alive_good += 1 # Increment current good count
            except ValidationError as validation_error:
                 logging.error(f"Validation Error processing player state {p_dict.get('id', 'N/A')} during win check: {validation_error}")
                 continue
            except Exception as e:
                 logging.error(f"Error processing player state {p_dict.get('id', 'N/A')} during win check: {e}", exc_info=True)
                 continue

        # --- Determine winner based on CURRENT counts ---
        winner_color = "yellow" # Default color
        if current_alive_imps == 0 and current_alive_good > 0:
             winner = 'Good'
             winner_color = "green"
        # --- Use current_alive_imps in the condition ---
        elif current_alive_imps > 0 and current_alive_good <= current_alive_imps:
             winner = 'Evil'
             winner_color = "magenta"
        # ----------------------------------------------
        else: # Draw or unexpected state (e.g., all dead?)
             if current_alive_good == 0 and current_alive_imps == 0:
                winner = 'Draw (All Dead)' # More specific Draw
                winner_color = "yellow"
             else: # Should not happen in basic setup? Maybe Imp alive but Good > Imp? (Game continues)
                  # This node should only be reached on game over conditions from graph edges
                  winner = 'Error/Undetermined' # Should not normally be reached if graph logic is correct
                  winner_color = "red"
                  logging.error(f"Unexpected state in set_winner_and_end: Imps Alive={current_alive_imps}, Good Alive={current_alive_good}")

        console.print(f"Winner determined: [{winner_color}]{winner}[/{winner_color}] (Alive Imps: {current_alive_imps}, Alive Good: {current_alive_good})")

    # --- Role Reveal ---
    console.print("\n[bold]--- Final Roles ---[/bold]")
    if player_details_list:
        # Sort by ID for consistent output
        for p_detail in sorted(player_details_list, key=lambda x: x.get('id', '')):
            role_color = "magenta" if p_detail.get('role') == 'Imp' else "green"
            status_color = "white" if p_detail.get('status') == 'alive' else "dim red"
            status_text = str(p_detail.get('status', 'unknown')).capitalize()
            console.print(f" - {p_detail.get('id', 'Unknown')}: Role=[{role_color}]{p_detail.get('role', 'Unknown')}[/{role_color}], Status=[{status_color}]{status_text}[/{status_color}]")
    else:
        console.print("[yellow]Could not retrieve final player details.[/yellow]")
    # ------------------

    log_entry = f"SYS: GAME OVER! The [bold {winner_color}]{winner}[/bold {winner_color}] team wins!"
    console.print(f"\n[bold {winner_color}]GAME OVER! The {winner} team wins![/bold {winner_color}]")

    # --- Update Final State ---
    state["game_over"] = True
    state["winner"] = winner
    # Append final log entry
    state["public_log"] = state.get('public_log', []) + [log_entry]
    state["current_phase"] = "GameOver"

    logging.info("set_winner_and_end complete.")
    return state