# main.py
import sys
import argparse # Import argparse
import logging # Import logging
from src.game_runner import run_game_sync
from rich.console import Console

# --- Global Console Instance ---
console = Console()

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Run the Social Deduction Game.")
parser.add_argument(
    "-d", "--debug",
    action="store_true", # Sets debug to True if flag is present
    help="Enable detailed INFO and DEBUG level logging."
)
parser.add_argument(
    "--human",
    default="Human", # Default human player ID
    help="Specify the ID for the human player."
)
# Add more arguments here if needed (e.g., player names, number of players)

args = parser.parse_args() # Parse arguments from sys.argv

# --- Configure Logging Level ---
log_level = logging.DEBUG if args.debug else logging.WARNING # DEBUG if --debug, else WARNING
# Use basicConfig BEFORE any logging happens
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # Force=True might be needed if logging was configured implicitly before this
    # force=True
)
# Optional: Silence noisy libraries if needed
# logging.getLogger("httpx").setLevel(logging.WARNING)


if __name__ == "__main__":
    # Basic player setup (can be enhanced with command-line args later)
    players = ["Alice", "Bob", "Charlie", "David", args.human] # Use human ID from args

    # Ensure the specified human player is actually in the list
    # (Could happen if user provides --human but not enough default players)
    if args.human not in players:
         # Basic correction: replace last element or add if empty
         if players:
             old_last = players[-1]
             console.print(f"[yellow]Replacing default player '{old_last}' with specified human '{args.human}'[/yellow]")
             players[-1] = args.human
         else:
             players.append(args.human)


    console.print(f"Starting game with players: {players}")
    console.print(f"Human player: [bold cyan]{args.human}[/bold cyan]")
    console.print(f"Logging Level: {logging.getLevelName(log_level)}") # Show the level

    # Pass the necessary info to the runner
    run_game_sync(player_list=players, human_player_id=args.human)