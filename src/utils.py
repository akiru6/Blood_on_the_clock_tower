# src/utils.py
from typing import Optional, List, Tuple # Correct import for Tuple
from .state import PlayerState, GameState, GraphState # Use GraphState for input dict type

def get_actor_and_targets(state_dict: GraphState, role_to_find: str) -> tuple[Optional[PlayerState], List[PlayerState]]:
    """
    Generic helper to find an alive player with a specific role and their potential targets.
    Targets are other alive players.
    """
    try:
        current_game_state = GameState.model_validate(state_dict)
    except Exception as e:
         print(f"ERROR parsing state in get_actor_and_targets: {e}")
         return None, []

    actor_player: Optional[PlayerState] = None
    for player in current_game_state.players:
        if player.role == role_to_find and player.status == 'alive':
            actor_player = player
            break

    if not actor_player:
        return None, []

    potential_targets = [
        p for p in current_game_state.players
        if p.status == 'alive' and p.id != actor_player.id
    ]
    return actor_player, potential_targets