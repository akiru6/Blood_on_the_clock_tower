# src/game_runner.py
from typing import Optional
import logging
import re

try:
    from __main__ import console
except ImportError:
     from rich.console import Console
     console = Console() # Fallback

from .graph_setup import graph
from .nodes.utility_nodes import initialize_game
from .state import GraphState
import sys

def is_debug_enabled():
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def run_game_sync(player_list: list[str], human_player_id: str):
    """Runs the game synchronously using the stream method with Rich formatting."""
    if human_player_id not in player_list:
        console.print(f"[bold red]Error: Human player ID '{human_player_id}' not found in player list: {player_list}[/bold red]")
        return

    initial_setup_config = {"player_ids": player_list, "human_player_id": human_player_id}
    logging.info(f"Preparing initial game state with config: {initial_setup_config}")

    try:
        first_game_state: GraphState = initialize_game(initial_setup_config)
        logging.info("Initial game state created successfully.")
    except Exception as e:
         logging.error(f"ERROR during initial game setup: {e}", exc_info=True)
         console.print(f"[bold red]An error occurred during game initialization: {e}[/bold red]")
         return

    console.print("\n[bold blue]--- Starting Game Simulation ---[/bold blue]")
    try:
        last_state_yielded: Optional[GraphState] = None
        run_config = {"recursion_limit": 100}
        logging.info(f"Streaming graph with config: {run_config}")

        for step_output in graph.stream(first_game_state, run_config):
            if not isinstance(step_output, dict) or not step_output: continue
            node_name = list(step_output.keys())[0]
            state_yielded = step_output[node_name]
            if not isinstance(state_yielded, dict): continue

            last_state_yielded = state_yielded

            if is_debug_enabled():
                console.print(f"\n[bold magenta]--- Debug: Completed Step: {node_name} ---[/bold magenta]")
                console.print(f" [dim] Current Phase:[/dim] [yellow]{state_yielded.get('current_phase', 'N/A')}[/yellow]")
                alive_players_list = state_yielded.get('alive_players')
                if alive_players_list:
                     console.print(f" [dim] Alive Players:[/dim] {', '.join(sorted(alive_players_list))}")
                else:
                     console.print(f" [dim] Alive Players:[/dim] [red]N/A[/red]")

                last_log_entry = state_yielded.get('public_log', [])[-1:]
                if last_log_entry:
                    log_content = last_log_entry[0]
                    log_prefix = " [dim magenta] Debug Last Log:[/dim magenta]"
                    if ": \"" in log_content and any(p_id in log_content.split(':')[0] for p_id in player_list):
                         player_id_part = log_content.split(':')[0]
                         speech_part = log_content[len(player_id_part)+1:]
                         console.print(f"{log_prefix} {player_id_part}:{speech_part}")
                    else:
                         cleaned_log = re.sub(r"^(SYS|VOTE|SPEAK|VOTE_REVEAL|DIM): ", "", log_content) # Added DIM
                         cleaned_log = re.sub(r'\[/?(?:bold|italic|color|dim|strike|underline|blink|reverse|conceal|code|on\s+\w+|[a-z]+(?: on \w+)?|/?rule)\]', '', cleaned_log) # Improved rich tag removal
                         console.print(f"{log_prefix} [grey50]{cleaned_log}[/grey50]")

        console.print("\n[bold blue]--- Game Finished (Graph Execution Complete) ---[/bold blue]")
        if last_state_yielded:
             winner = last_state_yielded.get('winner', 'N/A')
             winner_color = "green" if winner == "Good" else "magenta" if winner == "Evil" else "yellow"
             console.print(f" [bold]Winner:[/bold] [{winner_color}]{winner}[/{winner_color}]")
             # REMOVED redundant phase print: console.print(f" [dim]Final Phase:[/dim] [yellow]{last_state_yielded.get('current_phase', 'N/A')}[/yellow]")
             final_alive = last_state_yielded.get('alive_players', [])
             if final_alive:
                 console.print(f" [dim]Final Alive Players:[/dim] {', '.join(sorted(final_alive))}")
             else:
                  console.print(f" [dim]Final Alive Players:[/dim] [red]N/A[/red]")
             # Note: Role reveal is now printed within the set_winner_and_end node itself
        else:
             console.print("[bold red]Error: Could not determine final state.[/bold red]")

    except Exception as e:
        logging.error(f"\n--- An error occurred during graph execution ---", exc_info=True)
        console.print(f"\n[bold red]--- An error occurred during game execution ---[/bold red]")
        console.print(f"[red]{e}[/red]")
        if last_state_yielded:
             logging.error(f"Last known state before error: {last_state_yielded}")
             if is_debug_enabled():
                  console.print("[dim]Last known state logged for debugging:[/dim]")
                  console.print(f"[dim]{last_state_yielded}[/dim]")