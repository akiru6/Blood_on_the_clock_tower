# src/graph_setup.py
from langgraph.graph import StateGraph, END
# --- MODIFIED: Replace star import with explicit imports ---
# from .nodes import * # Original line (comment out or delete)
from .nodes import ( # Add explicit imports
    start_night_phase, imp_action, investigator_action,
    start_day_announce, discussion_phase, voting_phase, tally_votes,
    announce_process_execution, announce_no_execution,
    set_winner_and_end
)

from .state import GraphState, PlayerState # Import GraphState here

# --- Graph Builder ---
graph_builder = StateGraph(GraphState)

# --- Add Nodes ---
# ... (nodes remain the same) ...
graph_builder.add_node("start_night", start_night_phase)
graph_builder.add_node("imp_action", imp_action)
graph_builder.add_node("investigator_action", investigator_action)
graph_builder.add_node("start_day_announce", start_day_announce)
graph_builder.add_node("discussion", discussion_phase)
graph_builder.add_node("voting", voting_phase)
graph_builder.add_node("tally_votes", tally_votes)
graph_builder.add_node("announce_process_execution", announce_process_execution)
graph_builder.add_node("announce_no_execution", announce_no_execution)
graph_builder.add_node("set_winner_end", set_winner_and_end)

# --- Define Conditional Logic (MODIFIED) ---

def check_game_over_after_night(state: GraphState) -> str:
    """Checks win conditions after night actions / before day starts."""
    players = state.get('players', [])
    if not players: return "continue_day" # Should not happen, but safeguard

    # --- Calculate current alive counts directly from state ---
    alive_imps = 0
    alive_good = 0
    for p in players:
        if p.get('status') == 'alive':
            if p.get('role') == 'Imp':
                alive_imps += 1
            else: # Villager, Investigator, etc.
                alive_good += 1
    # ------------------------------------------------------

    # Game over conditions
    if alive_imps == 0:
        print("Condition (After Night): Game Over (Impostor eliminated - Good Wins).")
        return "game_over_early"
    # Evil wins if number of good players is less than or equal to number of impostors
    elif alive_good <= alive_imps:
        print(f"Condition (After Night): Game Over (Good <= Imp - Evil Wins). Imp:{alive_imps}, Good:{alive_good}")
        return "game_over_early"
    else:
        print("Condition (After Night): Continue Day.")
        return "continue_day"


def check_execution(state: GraphState) -> str:
    # This function remains the same
    if state.get("execution_target"):
        print("Condition J: Execution target found -> execute_player")
        return "execute_player"
    else:
        print("Condition J: No execution target -> no_execution")
        return "no_execution"

def check_game_over_final(state: GraphState) -> str:
    """Checks win conditions after execution / before night starts."""
    players = state.get('players', [])
    if not players: return "continue_night" # Safeguard

    # --- Calculate current alive counts directly from state ---
    alive_imps = 0
    alive_good = 0
    for p in players:
        if p.get('status') == 'alive':
            if p.get('role') == 'Imp':
                alive_imps += 1
            else: # Villager, Investigator, etc.
                alive_good += 1
    # ------------------------------------------------------

    # Game over conditions (same logic as after night check)
    if alive_imps == 0:
          print("Condition M: Game Over (Imp Dead - Good Wins).")
          return "game_over_final"
    # Evil wins if number of good players is less than or equal to number of impostors
    elif alive_good <= alive_imps:
          print(f"Condition M: Game Over (Imps win - Imp:{alive_imps} vs Good:{alive_good}).")
          return "game_over_final"
    else:
          print("Condition M: Continue Game.")
          return "continue_night"


# --- Add Edges ---
# ... (Edges remain the same) ...
graph_builder.set_entry_point("start_night")
graph_builder.add_edge("start_night", "imp_action")
graph_builder.add_edge("imp_action", "investigator_action")
graph_builder.add_edge("investigator_action", "start_day_announce")
graph_builder.add_conditional_edges( "start_day_announce", check_game_over_after_night,
                                   {"game_over_early": "set_winner_end", "continue_day": "discussion"})
graph_builder.add_edge("discussion", "voting")
graph_builder.add_edge("voting", "tally_votes")
graph_builder.add_conditional_edges(
    "tally_votes", check_execution,
    {"execute_player": "announce_process_execution", "no_execution": "announce_no_execution"}
)
graph_builder.add_conditional_edges(
    "announce_process_execution", check_game_over_final,
    {"game_over_final": "set_winner_end", "continue_night": "start_night"}
)
graph_builder.add_conditional_edges(
    "announce_no_execution", check_game_over_final,
    {"game_over_final": "set_winner_end", "continue_night": "start_night"}
)
graph_builder.add_edge("set_winner_end", END)


# --- Compile Graph ---
try:
    graph = graph_builder.compile()
    print("\nGraph compiled successfully with 'investigator_action' node!")
except Exception as e:
    print(f"\nError compiling graph: {e}", exc_info=True); raise e