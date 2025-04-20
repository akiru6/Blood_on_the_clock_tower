# src/ai_schemas.py
from pydantic import BaseModel, Field
# --- Literal is no longer needed for SpeechOutput intent/tone ---
from typing import Literal, Optional

# --- BaseTargetSelection and other schemas remain the same ---
class BaseTargetSelection(BaseModel):
    """
    Base schema for actions where the primary output is selecting
    a target player from a list of options using a key.
    """
    chosen_option_key: str = Field(
        ...,
        description="The single numerical key (e.g., '1', '2', '3') corresponding to the target player, chosen *only* from the provided options list."
    )
    reasoning: str = Field(
        ...,
        description="A brief explanation (1-2 sentences) justifying the choice of this target, based on game events, discussion, or role objectives."
    )

class VoteDecision(BaseTargetSelection):
    """Output schema for the AI's decision during a voting phase."""
    pass # Inherits fields and descriptions

class KillDecision(BaseTargetSelection):
    """Output schema for the Impostor's kill decision during the night phase."""
    reasoning: str = Field(
        ...,
        description="Impostor's brief internal thought (1-2 sentences) explaining why this target was chosen for elimination (e.g., perceived threat, suspicion level, strategic value). This is for analysis/debugging."
    ) # Overrides reasoning description slightly

class ProtectDecision(BaseTargetSelection):
    """Output schema for a Doctor's protection decision (if implemented)."""
    reasoning: str = Field(
        ...,
        description="Protector's rationale for choosing this player to save (e.g., perceived importance, likely Impostor target, self-preservation)."
    ) # Example for another role

class InvestigateDecision(BaseTargetSelection):
    """Output schema for an Investigator's check decision."""
    reasoning: str = Field(
        ...,
        description="Investigator's rationale for choosing this player to investigate (e.g., suspicious behavior, previous claims, process of elimination, testing trust)."
    ) # Overrides reasoning description for Investigator context


# --- MODIFIED Speech Schema (Relaxed intent/tone validation) ---
class SpeechOutput(BaseModel):
    """
    Output schema for the AI's statement during a discussion phase.
    Includes the intent behind the speech and a potential target.
    Intent and tone validation are relaxed to accept any string.
    """
    speech_content: str = Field(
        ...,
        description="The exact statement the player makes (1-3 sentences). Should be consistent with their role (Villager, Impostor, Investigator, etc.) and the current game situation."
    )
    # --- CHANGED intent type to Optional[str] ---
    intent: Optional[str] = Field(
        default='general_statement', # Default remains useful
        description="The primary intention behind this speech act (as provided by the LLM)."
    )
    # --- target_player remains the same ---
    target_player: Optional[str] = Field(
        default=None,
        description="The player ID this speech is primarily directed at (e.g., who is being asked, accused, responded to, contradicted)."
    )
    # --- CHANGED tone type to Optional[str] ---
    tone: Optional[str] = Field(
       default='neutral', # Default remains useful
       description="The primary tone of the speech (as provided by the LLM)."
    )