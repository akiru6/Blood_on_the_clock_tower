# src/state.py
from typing import Optional, List, Dict, Any, TypedDict, Literal
from pydantic import BaseModel, Field

# --- Pydantic Models (Reference/Internal Validation) ---

class PlayerState(BaseModel):
    id: str = Field(...)
    # --- Added Investigator Role ---
    role: Literal['Imp', 'Villager', 'Investigator'] = Field(...)
    # -----------------------------
    status: Literal['alive', 'dead'] = Field(default='alive')
    is_human: bool = Field(...)
    # --- Potential Field for Private Info (Optional, consider alternatives first) ---
    # private_knowledge: Dict[str, Any] = Field(default_factory=dict) # e.g., {'investigation_round_1': 'Alice is Good'}
    # -------------------------------------------------------------------
    class Config: validate_assignment = True

class GameState(BaseModel): # Pydantic model for reference/internal validation
    players: List[PlayerState] = Field(...)
    current_phase: Literal[
        'Initialising', 'Night', 'Day_Announce', 'Discussion',
        'Voting', 'Execution', 'GameOver'
    ] = Field(default='Initialising')
    round_number: int = Field(default=0)
    alive_players: List[str] = Field(default_factory=list)
    votes: Dict[str, str] = Field(default_factory=dict)
    execution_target: Optional[str] = Field(default=None)
    game_over: bool = Field(default=False)
    winner: Optional[Literal['Good', 'Evil']] = Field(default=None)
    public_log: List[str] = Field(default_factory=list)
    previous_round_votes: Dict[str, str] = Field(default_factory=dict)
    target_of_night_action: Optional[str] = Field(default=None) # Keep for Imp kill
    last_victim: Optional[str] = Field(default=None)
    last_executed: Optional[str] = Field(default=None)
    # --- Field for Pending Night Results (e.g., Investigation) ---
    # Stores results before they are delivered/processed. Cleared each day.
    # Format: {recipient_id: {action_type: result_details}}
    # Example: {'Investigator1': {'investigation': 'Alice is Villager'}}
    pending_night_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # -----------------------------------------------------------
    class Config: validate_assignment = True


# --- TypedDicts for Graph State ---

class GraphState(TypedDict):
    """Matches GameState structure for LangGraph."""
    players: List[Dict]
    current_phase: str
    round_number: int
    alive_players: List[str]
    votes: Dict[str, str]
    execution_target: Optional[str]
    game_over: bool
    winner: Optional[str]
    public_log: List[str]
    previous_round_votes: Dict[str, str]
    target_of_night_action: Optional[str] # Keep for Imp kill specifically? Or make generic? Let's keep for now.
    last_victim: Optional[str]
    last_executed: Optional[str]
    # --- Field for Pending Night Results ---
    pending_night_results: Dict[str, Dict[str, Any]] # e.g., {'Investigator1': {'investigation': 'Alice is Villager'}}
    # -------------------------------------


class ActionContext(TypedDict):
    """Context for the generic decision function."""
    # --- Added investigate ---
    action_type: Literal['speak', 'vote', 'imp_kill', 'investigate'] # Add other roles later
    # -----------------------
    player_id: str
    is_human: bool
    options: Optional[Dict[str, str]] = None
    prompt_message: Optional[str] = None
    full_game_state: GraphState
    player_role: Optional[str]