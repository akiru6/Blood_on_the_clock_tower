# src/llm_interface.py
import os
import asyncio # Import asyncio
import traceback
# --- REMOVED httpx ---
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel
from dotenv import load_dotenv
import logging

from rich.live import Live
from rich.markup import escape
try:
    from __main__ import console
except ImportError:
     print("Warning: Could not import global console from __main__. Rich output might be limited.")
     from rich.console import Console
     console = Console()

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.exceptions import UnexpectedModelBehavior, ModelHTTPError
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta, PartStartEvent

# ... (load_dotenv, api key check, model name, system prompt, base url) ...
load_dotenv()
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
if not openrouter_api_key:
     raise EnvironmentError("ERROR: Missing environment variable: OPENROUTER_API_KEY.")

OPENROUTER_MODEL_NAME = "deepseek/deepseek-chat-v3-0324:free"
DEFAULT_MODEL_PARAMS = {"temperature": 0.7}
DEFAULT_SYSTEM_PROMPT = "You are an AI player in a social deduction game."
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# --- Define timeout constant ---
LLM_CALL_TIMEOUT_SECONDS = 60.0
# -----------------------------

_plain_text_agent: Optional[Agent] = None

def _get_plain_text_agent() -> Optional[Agent]:
    """
    Creates agent using simple provider config.
    """
    global _plain_text_agent
    if _plain_text_agent: return _plain_text_agent
    if openrouter_api_key: logging.info("Found OPENROUTER_API_KEY env var.")
    else: logging.error("OPENROUTER_API_KEY missing during agent config!"); return None
    logging.info(f"Configuring agent: {OPENROUTER_MODEL_NAME} via OpenRouter")
    try:
        provider = OpenAIProvider(api_key=openrouter_api_key, base_url=OPENROUTER_BASE_URL)
        model = OpenAIModel(OPENROUTER_MODEL_NAME, provider=provider)
        agent = Agent(model=model, system_prompt=DEFAULT_SYSTEM_PROMPT)
        _plain_text_agent = agent
        logging.info("Agent configured successfully.")
        return agent
    except Exception as e:
        logging.error(f"ERROR: Failed to configure Agent: {e}", exc_info=True)
        console.print(f"[bold red]Error configuring AI Agent: {e}[/bold red]")
        return None

# --- MODIFIED get_llm_response_string with asyncio.wait_for ---
async def _actual_llm_call(agent_instance, user_prompt, enable_streaming, player_id):
    """Helper async function containing the core LLM interaction."""
    ai_response_str = ""
    color = "cyan"
    # This inner function contains the original logic for streaming/non-streaming
    if enable_streaming:
        live_display_content = f"[{color}]{player_id}: [/]"
        try:
            with Live(live_display_content, console=console, auto_refresh=False, vertical_overflow="visible", transient=True) as live:
                async with agent_instance.iter(
                    user_prompt,
                    model_settings=DEFAULT_MODEL_PARAMS
                    ) as run:
                    async for node in run:
                        if Agent.is_model_request_node(node):
                            async with node.stream(run.ctx) as request_stream:
                                async for event in request_stream:
                                    # ... (delta processing logic) ...
                                    delta_content = ""
                                    if isinstance(event, PartStartEvent) and hasattr(event.part, 'content') and isinstance(event.part.content, str):
                                        if not ai_response_str: delta_content = event.part.content
                                    elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                                        delta_content = event.delta.content_delta
                                    if delta_content:
                                        ai_response_str += delta_content
                                        live.update(f"[{color}]{player_id}: {escape(ai_response_str)}[/{color}]", refresh=True)
        except Exception as live_err: # Catch Rich Live errors specifically
            logging.error(f"Error with Rich Live display for {player_id}: {live_err}", exc_info=True)
            console.print(f"[bold red]Error setting up Rich Live display: {live_err}[/bold red]")
            raise # Re-raise to be caught by outer handler
    else: # Non-Streaming
         async with agent_instance.iter(
             user_prompt,
             model_settings=DEFAULT_MODEL_PARAMS
             ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            # ... (delta processing logic) ...
                            if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                                ai_response_str += event.delta.content_delta
                            elif isinstance(event, PartStartEvent) and hasattr(event.part, 'content') and isinstance(event.part.content, str):
                                 if event.index == 0 and not ai_response_str:
                                      ai_response_str = event.part.content
    return ai_response_str.strip()


async def get_llm_response_string(
    system_prompt: str, # Keep for logging/context clarity maybe, though agent uses its own
    user_prompt: str,
    player_id: str,
    enable_streaming: bool = False
) -> Optional[str]:
    """
    Runs the plain text agent, using asyncio.wait_for for timeout control.
    """
    agent_instance = _get_plain_text_agent()
    if not agent_instance:
        logging.error(f"Cannot get LLM response for {player_id}: Agent instance not configured.")
        return None

    logging.info(f"--- Calling Agent ({OPENROUTER_MODEL_NAME} via OR) for {player_id} (Streaming: {enable_streaming}) ---")
    logging.debug(f"User Prompt (start): {user_prompt[:300]}...")

    final_string: Optional[str] = None
    try:
        # --- Use asyncio.wait_for to wrap the actual call ---
        final_string = await asyncio.wait_for(
            _actual_llm_call(agent_instance, user_prompt, enable_streaming, player_id),
            timeout=LLM_CALL_TIMEOUT_SECONDS
        )
        # ----------------------------------------------------
        logging.info(f"--- Agent call completed for {player_id}. ---")
        if logging.getLogger().isEnabledFor(logging.DEBUG):
             logging.debug(f"LLM String Result (Final): '{final_string}'")
        else:
             logging.info(f"LLM String Result (Final): '{final_string[:70]}...'")
        if not final_string: # Check if empty after successful call
             logging.warning(f"LLM returned an empty string for {player_id} after processing.")
             console.print(f"[yellow]Warning: AI ({player_id}) returned an empty response.[/yellow]")

    # --- Catch specific TimeoutError from asyncio.wait_for ---
    except TimeoutError: # Note: This is asyncio.TimeoutError in newer Python, just TimeoutError often works
        logging.error(f"LLM call TIMED OUT for {player_id} after {LLM_CALL_TIMEOUT_SECONDS}s (asyncio.wait_for).")
        console.print(f"[bold red]Error: AI ({player_id}) call timed out.[/bold red]")
        return None # Signal failure
    # ------------------------------------------------------
    except ModelHTTPError as http_err: # Catch API errors from pydantic-ai
        logging.error(f"API Error during agent call for {player_id}: {http_err}", exc_info=True)
        console.print(f"[bold red]API Error during AI call for {player_id}: {http_err}. See logs.[/bold red]")
        return None
    except UnexpectedModelBehavior as e: # Catch pydantic-ai specific errors
         logging.error(f"ERROR (UnexpectedModelBehavior) during Agent interaction for {player_id}: {e}", exc_info=False)
         console.print(f"[bold red]LLM Error ({player_id}): {e}[/bold red]")
         return None
    except Exception as e: # Catch any other errors during the call or processing
        error_message = f"ERROR during Agent interaction or processing for {player_id}: {e.__class__.__name__}: {e}"
        logging.error(error_message, exc_info=True)
        console.print(f"[bold red]Agent Interaction Error ({player_id}): {e}. See logs.[/bold red]")
        return None

    return final_string # Return the result if successful