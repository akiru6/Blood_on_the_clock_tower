# src/narrator_utils.py
"""
Utilities for generating narrative text for the game, enhancing immersion
and providing clearer context during gameplay.

These functions generate strings intended primarily for console output,
but parts might be adapted for logging. They aim to provide flavorful
descriptions that can serve as examples for future LLM-based narration.
"""

from typing import Optional, Dict, List, Counter as TypingCounter # Added Counter
import random

# --- Phase Start Narratives ---

def narrate_night_begins(round_number: int) -> str:
    """Generates narrative text for the beginning of the night phase."""
    phrases = [
        "The moon hangs high, casting long, eerie shadows across the silent town. Night falls, and Round {round_number} begins under its dark cloak.",
        "Silence descends as the sun dips below the horizon. Darkness creeps in, marking the start of Round {round_number}. What terrors will this night hold?",
        "As villagers seek refuge in their homes, a chilling quiet settles. The night phase of Round {round_number} has commenced. Eyes watch from the shadows.",
    ]
    chosen_phrase = random.choice(phrases).format(round_number=round_number)
    return f"\n[bold blue]🌙 {chosen_phrase}[/bold blue]"

def narrate_day_begins(round_number: int) -> str:
    """Generates narrative text for the beginning of the day phase (before knowing the night's outcome)."""
    phrases = [
        "Dawn breaks, painting the sky in hues of hope and trepidation. The town slowly stirs as Day {round_number} begins.",
        "The first rays of sunlight pierce the lingering darkness. Villagers emerge cautiously to face Day {round_number}.",
        "A new day arrives, heavy with the weight of the night's uncertainty. Day {round_number} is here.",
    ]
    chosen_phrase = random.choice(phrases).format(round_number=round_number)
    return f"\n[bold yellow]☀️ {chosen_phrase}[/bold yellow]"


# --- Event Announcement Narratives ---

def narrate_death_announcement(victim_id: str) -> str:
    """Generates narrative text announcing a player's death."""
    phrases = [
        "A grim discovery casts a pall over the morning. [bold red]{victim_id}[/bold red] lies still, a victim of the night's unseen horrors.",
        "The fragile peace of dawn is shattered. Tragedy has struck – [bold red]{victim_id}[/bold red] did not survive the night.",
        "Fear grips the town as the terrible news spreads: [bold red]{victim_id}[/bold red] has been found dead.",
    ]
    chosen_phrase = random.choice(phrases).format(victim_id=victim_id)
    return f"[yellow]{chosen_phrase}[/yellow]"

def narrate_no_death() -> str:
    """Generates narrative text when no one died during the night."""
    phrases = [
        "A tense silence hangs in the air. Against all odds, everyone seems to have survived the night. But the danger is far from over.",
        "Miraculously, the night passed without bloodshed. Yet, as villagers exchange uneasy glances, suspicion lingers palpably.",
        "Dawn arrives with a sigh of relief, but little comfort. No one fell victim to the darkness this time, but the impostor remains among us.",
    ]
    chosen_phrase = random.choice(phrases)
    return f"[green]{chosen_phrase}[/green]"


# --- Vote and Execution Narratives (NEW) ---

def narrate_vote_results(
    vote_counts: TypingCounter[str],
    execution_target: Optional[str],
    tied_players: Optional[List[str]] # Make optional
    ) -> str:
    """Generates narrative text summarizing the vote results."""
    narrative_parts = []
    vote_phrases = [
        "The tension is palpable as the votes are revealed.",
        "All eyes turn to the center of the town square as the tally is announced.",
        "The moment of judgment arrives. The votes have been counted.",
    ]
    narrative_parts.append(f"[bold yellow]{random.choice(vote_phrases)}[/bold yellow]")

    if not vote_counts:
        no_votes_phrases = [
            "Strangely, no votes were cast.",
            "An eerie silence follows the call for votes. None were submitted.",
            "The ballot box remains empty.",
        ]
        narrative_parts.append(f"[yellow]{random.choice(no_votes_phrases)}[/yellow]")
        narrative_parts.append("[yellow]No one faces execution today.[/yellow]")
    else:
        counts_summary = ", ".join(f"[bold]{p}[/bold]: {c}" for p, c in vote_counts.most_common())
        narrative_parts.append(f"The final counts are: {counts_summary}.")

        if execution_target:
            exec_target_phrases = [
                f"With the most votes cast against them, [bold red]{execution_target}[/bold red] stands accused.",
                f"The town's suspicion coalesces. [bold red]{execution_target}[/bold red] receives the most votes.",
                f"By majority decision, [bold red]{execution_target}[/bold red] has been singled out.",
            ]
            narrative_parts.append(f"[yellow]{random.choice(exec_target_phrases)}[/yellow]")
        elif tied_players:
            tie_phrases = [
                f"The vote is split! A tie between {', '.join(f'[yellow bold]{p}[/yellow bold]' for p in tied_players)} means no one faces the gallows today.",
                f"Indecision grips the town. With votes tied for {', '.join(f'[yellow bold]{p}[/yellow bold]' for p in tied_players)}, execution is stayed.",
                f"A deadlock! {', '.join(f'[yellow bold]{p}[/yellow bold]' for p in tied_players)} received equal votes. Justice, or perhaps chaos, waits another day.",
            ]
            narrative_parts.append(f"[yellow]{random.choice(tie_phrases)}[/yellow]")
        else: # No majority, but votes were cast
             no_majority_phrases = [
                 "Despite the votes, no clear consensus emerged.",
                 "The accusations fly, but no single person receives enough votes for condemnation.",
                 "The town remains divided. No majority was reached.",
             ]
             narrative_parts.append(f"[yellow]{random.choice(no_majority_phrases)}[/yellow]")
             narrative_parts.append("[yellow]No one faces execution today.[/yellow]")


    return "\n".join(narrative_parts)


def narrate_execution(executed_player_id: str) -> str:
    """Generates narrative text for a player's execution."""
    phrases = [
        f"The sentence is carried out. [bold red]{executed_player_id}[/bold red] meets their fate at the hands of the town.",
        f"A heavy silence falls as [bold red]{executed_player_id}[/bold red] is executed. Was justice served, or has the town erred?",
        f"The town's judgment is final. [bold red]{executed_player_id}[/bold red] is no more.",
    ]
    chosen_phrase = random.choice(phrases).format(executed_player_id=executed_player_id)
    # Use a distinct style/color for execution
    return f"[bold magenta]{chosen_phrase}[/bold magenta]"


def narrate_no_execution(reason: str) -> str:
    """Generates narrative text when no execution occurs (reason provided)."""
    # This might be redundant if narrate_vote_results covers it, but can be used for clarity
    # or if the announcement happens in a separate node definitively.
    # Let's keep it simple for now, acknowledging narrate_vote_results already provides context.
    phrases = [
        f"Due to {reason.lower()}, the town square remains empty. There will be no execution today.",
        f"With the vote resulting in {reason.lower()}, the accused are spared... for now.",
        f"The proceedings halt. {reason} prevents an execution.",
    ]
    chosen_phrase = random.choice(phrases).format(reason=reason)
    return f"[yellow]{chosen_phrase}[/yellow]"

# --- Placeholder for future GM functions ---
# def narrate_gm_intervention(...)