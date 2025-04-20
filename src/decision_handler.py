# src/decision_handler.py
import asyncio
from typing import Optional, Any, Dict, List
import logging

# --- ADDED: Import SpeechOutput for creating the dict ---
from .ai_schemas import SpeechOutput
# -------------------------------------------------------

try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console()

from .state import ActionContext
from .ai_player import get_ai_decision_logic

# --- MODIFIED Human Decision for Speak ---
def _get_human_decision_via_input(context: ActionContext) -> Optional[Any]:
    """Gets decision from a human player via console input using Rich."""
    player_id = context['player_id']
    action_type = context['action_type']
    prompt_msg = context.get('prompt_message', "Decision needed:")
    options = context.get('options')

    console.print(f"\n[bold green]--- Human Player '{player_id}', Action ({action_type}) ---[/bold green]")
    console.print(f"[green]{prompt_msg}[/green]")

    if options: # Handling for vote, investigate, etc. (remains the same)
        while True:
            try:
                if not all(f"{k}: {v}" in prompt_msg for k,v in options.items()):
                    console.print("[bold]Options:[/bold]")
                    for key, value in options.items():
                        console.print(f"  [yellow]{key}[/yellow]: {value}")
                choice_key = console.input("[bold]Enter the key:[/bold] ")
                if choice_key in options:
                    console.print(f"Selected: {options[choice_key]} (Key: [yellow]{choice_key}[/yellow])")
                    return choice_key # Return the key string
                else:
                    console.print("[bold red]Invalid key.[/bold red] Please choose from the provided options.")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Input cancelled by user.[/yellow]")
                return None
    # --- MODIFIED: Handling for 'speak' action ---
    elif action_type == 'speak':
        try:
            user_input = console.input("[bold]Enter input:[/bold] ")
            if user_input is None or not user_input.strip(): # Handle empty input or cancellation
                console.print("\n[yellow]Input cancelled or empty.[/yellow]")
                # Return a dict representing silence/failure for consistency?
                # Or let the node handle None? Let's return None for now.
                # The node's 'else' block already handles None as silence.
                return None
            else:
                # Wrap the human speech into the SpeechOutput structure
                # For now, default intent and tone. Could ask human later.
                speech_dict = {
                    "speech_content": user_input.strip(),
                    "intent": "general_statement", # Default intent for human for now
                    "target_player": None,         # Default target for human for now
                    "tone": "neutral"              # Default tone for human for now
                }
                logging.info(f"Human input packaged as SpeechOutput dict: {speech_dict}")
                # We don't need to validate here, assume human input is content.
                # The receiving node expects a dict.
                return speech_dict # Return the dictionary
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Input cancelled by user.[/yellow]")
            return None
    # --- End Modification ---
    else:
        # Fallback for other action types without options (if any)
        try:
            user_input = console.input("[bold]Enter input:[/bold] ")
            return user_input # Return raw string for unknown types
        except (EOFError, KeyboardInterrupt):
            print("\n[yellow]Input cancelled by user.[/yellow]")
            return None


# --- Unified Decision Entry Point (remains the same) ---
async def get_decision(context: ActionContext) -> Optional[Any]:
    """Calls Human input or AI logic, logging appropriately."""
    player_id = context['player_id']
    action_type = context['action_type']
    role = context.get('player_role', 'Unknown')

    PUBLIC_ACTIONS: List[str] = ['speak', 'vote']
    SECRET_ACTIONS: List[str] = ['imp_kill', 'investigate']

    if context['is_human']:
        logging.debug(f"Handling synchronous human input for {player_id} ({action_type})")
        # Now returns string (key) or dict (speak) or None
        return _get_human_decision_via_input(context)
    else:
        logging.info(f"--- AI Player '{player_id}' ({role}) taking Action: {action_type} ---")
        if action_type in PUBLIC_ACTIONS:
             console.print(f"[dim cyan]轮到 {player_id} (AI) {action_type}...[/dim cyan]")
        elif action_type in SECRET_ACTIONS:
             logging.info(f"AI Player {player_id} ({role}) performing secret action: {action_type}")
        else:
             console.print(f"[yellow]AI Player {player_id} ({role}) performing unknown action: {action_type}...[/yellow]")

        # Returns string (key) or dict (speak) or failure dict or None
        return await get_ai_decision_logic(context)