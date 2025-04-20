# LangGraph Social Deduction Game Simulation (Blood on the Clocktower - Inspired)

This project simulates a social deduction game framework inspired by games like Mafia, Werewolf, and Blood on the Clocktower. It utilizes LangGraph for managing the game's state and flow, integrating both human console input and AI players driven by Large Language Models (LLMs) via Pydantic-AI and OpenRouter.

## Project Goal

To create a flexible and extensible Python framework for simulating turn-based social deduction games, allowing for complex state management, conditional game flow, and dynamic decision-making by different player types (human/AI).

## Current Status (As of 2025-03-31)

*   **WORKING:** The core game loop is functional with the **Plain Text + OpenRouter** approach for AI.
*   **Game Flow:** Successfully simulates Night phase (Impostor kill), Day phase (Announcement, Discussion, Voting, Tallying, Execution/No Execution), role assignment, and win condition checking.
*   **AI Players:** AI players successfully use an LLM (configured via OpenRouter, e.g., Mistral 7B Instruct) to generate speech and make targeting/voting decisions based on game state and role prompts.
*   **Human Player:** Fully interactive via the console for speaking and voting.
*   **Known Logging Quirk:** The state dictionary yielded by `graph.stream()` after each step accurately reflects the full state *now* because all nodes were modified to return the complete state dictionary. The previous "Key missing in yield" issue is resolved.

## Key Features Implemented

*   **LangGraph State Machine:** Manages transitions between `Night`, `Day_Announce`, `Discussion`, `Voting`, `Execution`, `GameOver` phases using `StateGraph`.
*   **Defined State:** Uses `TypedDict` (`GraphState`) and Pydantic `BaseModel` (`PlayerState`) for clear state structure.
*   **Modular Nodes:** Game logic is separated into node functions within `src/nodes/`.
*   **Human/AI Player Handling:** `decision_handler.py` routes requests based on player type.
*   **LLM Integration (Plain Text Mode):**
    *   Uses `pydantic-ai`'s `Agent` class configured for an OpenRouter model **without** `result_type` to get plain text responses.
    *   Connects via `OpenAIProvider` pointed at OpenRouter API.
    *   Builds context-aware prompts using base role instructions (`src/prompts/`) and dynamic game state (`_build_dynamic_context`).
    *   Includes specific instructions in prompts asking the LLM for plain text output in the desired format (e.g., "Reply ONLY with the key...").
    *   Uses `agent.run()` (non-streaming for simplicity now) in `llm_interface.py`.
*   **Response Parsing:** Basic string parsing (direct match, regex) in `ai_player.py` to extract keys from LLM vote/kill responses.
*   **Fallback Logic:** AI reverts to random placeholder actions if the LLM call fails or parsing is unsuccessful.
*   **Basic Roles:** 1 Impostor, rest Villagers.
*   **Win Conditions:** Checks for Impostor elimination or Impostor majority/parity.

## Technology Stack

*   **Python 3.10+** (Async/Await used)
*   **LangGraph:** Core framework (`langgraph`)
*   **Pydantic:** Data validation (`pydantic`)
*   **Pydantic-AI:** LLM interaction layer (`pydantic-ai`)
*   **OpenRouter:** LLM provider gateway (requires API key)
*   **Supporting Libraries:** `python-dotenv`, `httpx`, `openai`, `google-generativeai` (as dependencies of pydantic-ai providers)

## Project Structure
/
├── src/
│ ├── nodes/ # LangGraph node functions
│ │ ├── init.py
│ │ ├── day_nodes.py
│ │ ├── night_nodes.py
│ │ └── utility_nodes.py # set_winner_and_end node (initialize_game is helper)
│ ├── prompts/ # Base AI prompts
│ │ ├── impostor.txt
│ │ └── villager.txt
│ ├── init.py
│ ├── ai_player.py # AI logic (prompting, LLM call trigger, parsing, fallback)
│ ├── ai_schemas.py # Pydantic schemas (Currently for reference, not used for LLM call)
│ ├── decision_handler.py # Routes Human/AI decisions (now async)
│ ├── game_runner.py # Runs the game (calls initialize_game, graph.stream)
│ ├── graph_setup.py # Defines LangGraph StateGraph
│ ├── llm_interface.py # Configures pydantic-ai Agent (plain text), calls LLM API
│ ├── state.py # State definitions (PlayerState, GameState GraphState)
│ └── utils.py # Helper functions
├── .env # Store API keys (OPENROUTER_API_KEY) - Gitignored
├── .gitignore
├── main.py # Entry point: configure players, run game
├── requirements.txt # Dependencies
└── README.md # This file

## Core Concepts & Flow (Simplified)

1.  **Setup:** `main.py` defines players -> `game_runner.py` calls `initialize_game` helper -> Creates `first_game_state` dictionary.
2.  **Execution:** `game_runner.py` calls `graph.stream(first_game_state, config)`.
3.  **Graph Cycle:** LangGraph executes nodes (`start_night`, `imp_action`, etc.) based on edges and conditions.
4.  **State Update:** Each node receives the *full* `GraphState`, modifies it, and returns the *full modified* `GraphState`.
5.  **Logging:** `game_runner.py` iterates through `graph.stream()`, logging the complete state yielded after each node.
6.  **Decisions:** Nodes call `decision_handler.get_decision(context)`.
7.  **Human:** `get_decision` calls sync `_get_human_decision_via_input`.
8.  **AI:** `get_decision` awaits async `ai_player.get_ai_decision_logic`.
9.  **AI Logic:** `get_ai_decision_logic` builds prompts -> awaits `llm_interface.get_llm_response_string` -> gets plain text string -> parses string (for vote/kill) or uses directly (speak) -> returns result or triggers fallback.
10. **LLM Interface:** `get_llm_response_string` uses a cached `pydantic-ai` `Agent` (configured for OpenRouter, *no result_type*) -> calls `agent.run(prompt)` -> returns text data.
11. **Win Check:** Conditional edges check state -> transition to `set_winner_and_end` -> `END`.