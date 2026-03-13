"""Main Claude agent reasoning loop for Flora."""
from __future__ import annotations

import logging
from datetime import datetime

import anthropic

from flora.config import AppConfig
from flora.db import ActionRecord, Database, JournalEntry
from flora.agent.prompts import build_system_prompt, build_plant_context
from flora.agent.tools import TOOL_DEFINITIONS, ToolExecutor

logger = logging.getLogger(__name__)

# Safety fallback thresholds (when Claude API is unavailable)
FALLBACK_MOISTURE_THRESHOLD = 30.0
FALLBACK_WATER_DURATION = 10


class AgentLoop:
    """Runs the Claude reasoning loop for all plants."""

    def __init__(self, config: AppConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._executor = ToolExecutor(config, db)
        self._system_prompt = build_system_prompt()

    async def run_once(self) -> None:
        """Run one agent reasoning cycle for all plants."""
        logger.info("Agent loop started at %s", datetime.utcnow().isoformat())
        try:
            await self._run_claude_loop()
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s — falling back to rule-based", exc)
            await self._run_fallback()
        except Exception as exc:
            logger.error("Agent loop error: %s", exc, exc_info=True)

    async def _run_claude_loop(self) -> None:
        """Build context for all plants and run Claude with tool use."""
        ambient_reading = await self._db.get_latest_ambient()
        ambient_dict = None
        if ambient_reading:
            ambient_dict = {
                "temperature": ambient_reading.temperature,
                "humidity": ambient_reading.humidity,
            }

        plant_contexts: list[str] = []
        for plant in self._config.plants:
            readings = await self._db.get_sensor_history(plant.name, hours=168, limit=50)
            journals = await self._db.get_journal(plant.name, limit=20)

            recent_dicts = [
                {
                    "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "moisture": r.moisture,
                    "temperature": r.temperature,
                    "light": r.light,
                    "fertility": r.fertility,
                    "battery": r.battery,
                }
                for r in readings
            ]
            journal_dicts = [
                {
                    "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "entry_type": e.entry_type,
                    "content": e.content,
                }
                for e in journals
            ]

            plant_contexts.append(
                build_plant_context(
                    plant.name,
                    plant.species,
                    recent_dicts,
                    journal_dicts,
                    ambient_dict,
                )
            )

        user_message = (
            f"Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            "Please review all plants and take any necessary actions.\n\n"
            + "\n\n".join(plant_contexts)
        )

        messages: list[anthropic.types.MessageParam] = [
            {"role": "user", "content": user_message}
        ]

        # Agentic loop: continue until no more tool calls
        for iteration in range(10):  # safety limit
            response = await self._client.messages.create(
                model=self._config.anthropic_model,
                max_tokens=4096,
                system=self._system_prompt,
                tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
                messages=messages,
            )

            logger.debug("Agent iteration %d: stop_reason=%s", iteration, response.stop_reason)

            # Collect tool uses from this response
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # No more tool calls — agent is done
                logger.info("Agent loop completed after %d iterations", iteration + 1)
                break

            # Execute all tool calls
            tool_results: list[anthropic.types.ToolResultBlockParam] = []
            for tool_use in tool_uses:
                logger.info("Executing tool: %s", tool_use.name)
                result = await self._executor.execute(tool_use.name, tool_use.input)  # type: ignore[arg-type]
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            # Add assistant response + tool results to messages
            messages.append({"role": "assistant", "content": response.content})  # type: ignore[arg-type]
            messages.append({"role": "user", "content": tool_results})

    async def _run_fallback(self) -> None:
        """Rule-based fallback: water any plant with moisture < threshold."""
        logger.info("Running rule-based fallback for all plants")
        for plant in self._config.plants:
            reading = await self._db.get_latest_sensor_reading(plant.name)
            if reading is None:
                logger.warning("No reading for %s — skipping fallback", plant.name)
                continue

            if reading.moisture is not None and reading.moisture < FALLBACK_MOISTURE_THRESHOLD:
                logger.info(
                    "Fallback: watering %s (moisture=%.1f%%)",
                    plant.name, reading.moisture
                )
                from flora.actuators.pump import water_plant
                success = await water_plant(plant.pump_gpio, FALLBACK_WATER_DURATION)
                await self._db.log_action(ActionRecord(
                    plant_name=plant.name,
                    timestamp=datetime.utcnow(),
                    action_type="water_plant",
                    parameters={"duration_seconds": FALLBACK_WATER_DURATION, "mode": "fallback"},
                    reasoning=f"Rule-based fallback: moisture {reading.moisture:.1f}% < {FALLBACK_MOISTURE_THRESHOLD}%",
                    claude_model="fallback",
                ))
                await self._db.add_journal_entry(JournalEntry(
                    plant_name=plant.name,
                    timestamp=datetime.utcnow(),
                    entry_type="action",
                    content=f"Fallback watering: moisture was {reading.moisture:.1f}%. Claude API unavailable.",
                ))
