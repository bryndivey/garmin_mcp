"""
Strength / weight training plan authoring for Garmin Connect MCP Server.

Everything else in this server reads from Garmin. This module writes: it builds
Garmin's workout JSON from a compact exercise spec, uploads it to the workout
library, and schedules it onto the training calendar.
"""

import json
from typing import Any, Dict, List, Optional

from modules.exercise_catalogue import EXERCISES, category_for, is_valid

# The garmin_client will be set by the main file
garmin_client = None


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


# --- Garmin workout vocabulary -------------------------------------------------
# These enum ids are what Garmin's workout-service expects; the keys alone are
# not enough, the ids are what actually get validated.

SPORT_TYPE_STRENGTH = {
    "sportTypeId": 5,
    "sportTypeKey": "strength_training",
    "displayOrder": 5,
}

STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}

END_CONDITIONS = {
    "lap.button": {
        "conditionTypeId": 1,
        "conditionTypeKey": "lap.button",
        "displayOrder": 1,
        "displayable": True,
    },
    "time": {
        "conditionTypeId": 2,
        "conditionTypeKey": "time",
        "displayOrder": 2,
        "displayable": True,
    },
    "iterations": {
        "conditionTypeId": 7,
        "conditionTypeKey": "iterations",
        "displayOrder": 7,
        "displayable": False,
    },
    "reps": {
        "conditionTypeId": 10,
        "conditionTypeKey": "reps",
        "displayOrder": 10,
        "displayable": True,
    },
}

WEIGHT_UNIT_KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

def _normalise_exercise(name: str) -> str:
    """Turn 'barbell bench press' or 'Barbell Bench Press' into BARBELL_BENCH_PRESS."""
    return name.strip().upper().replace(" ", "_").replace("-", "_")


def _rest_step(step_order: int, child_step_id: int, seconds: int) -> Dict[str, Any]:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": STEP_TYPES["rest"],
        "childStepId": child_step_id,
        "endCondition": END_CONDITIONS["time"],
        "endConditionValue": float(seconds),
        "description": None,
    }


def _exercise_step(
    step_order: int,
    child_step_id: Optional[int],
    exercise: Dict[str, Any],
) -> Dict[str, Any]:
    """Build one executable strength step from a compact exercise spec."""
    name = _normalise_exercise(str(exercise.get("exercise", "")))
    if not name:
        raise ValueError("each exercise needs an 'exercise' name")

    category = exercise.get("category")
    if category:
        category = _normalise_exercise(str(category))
    else:
        category = category_for(name)
        if not category:
            raise ValueError(
                f"unknown exercise '{name}' — call list_strength_exercises to "
                "find the Garmin name for it"
            )

    # Garmin does not reject an unrecognised exerciseName, it silently stores an
    # empty one, which turns the step into a bare category on the watch. Catch
    # that here so a bad name fails loudly instead of quietly degrading.
    if not is_valid(category, name):
        suggestion = category_for(name)
        hint = (
            f" — '{name}' belongs to category '{suggestion}', not '{category}'"
            if suggestion
            else f" — no exercise named '{name}' exists in Garmin's catalogue"
        )
        raise ValueError(f"invalid exercise/category pairing{hint}")

    step: Dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": STEP_TYPES[exercise.get("step_type", "interval")],
        "childStepId": child_step_id,
        "category": category,
        "exerciseName": name,
        "description": exercise.get("notes"),
    }

    duration = exercise.get("duration_seconds")
    if duration:
        step["endCondition"] = END_CONDITIONS["time"]
        step["endConditionValue"] = float(duration)
    else:
        reps = exercise.get("reps")
        if reps is None:
            step["endCondition"] = END_CONDITIONS["lap.button"]
        else:
            step["endCondition"] = END_CONDITIONS["reps"]
            step["endConditionValue"] = float(reps)

    weight_kg = exercise.get("weight_kg")
    if weight_kg:
        # weightValue is in the unit named by weightUnit, i.e. plain kg. The
        # unit's 'factor' is metadata Garmin sends back, not a multiplier to
        # apply here — scaling by it renders 50kg as "50,000.0kg" in the app.
        step["weightValue"] = float(weight_kg)
        step["weightUnit"] = WEIGHT_UNIT_KG

    return step


def build_strength_workout(
    name: str, exercises: List[Dict[str, Any]], description: str = ""
) -> Dict[str, Any]:
    """Build the Garmin workout payload for a strength session.

    Each exercise dict accepts:
        exercise:         exercise name, e.g. "BARBELL_BACK_SQUAT" (required)
        category:         Garmin parent category; inferred from the catalogue if omitted
        sets:             number of sets (default 1; >1 wraps the step in a repeat group)
        reps:             reps per set; omit for a lap-button-terminated set
        weight_kg:        working weight in kg
        duration_seconds: use a timed set instead of reps (e.g. planks)
        rest_seconds:     rest after each set
        notes:            free text shown on the watch
    """
    if not exercises:
        raise ValueError("a workout needs at least one exercise")

    steps: List[Dict[str, Any]] = []
    step_order = 1
    child_step_id = 1

    for exercise in exercises:
        sets = int(exercise.get("sets", 1) or 1)
        rest = exercise.get("rest_seconds")

        if sets > 1:
            # Repeat group: the exercise step plus its rest repeat together.
            group_order = step_order
            step_order += 1
            inner: List[Dict[str, Any]] = [
                _exercise_step(step_order, child_step_id, exercise)
            ]
            step_order += 1
            if rest:
                inner.append(_rest_step(step_order, child_step_id, int(rest)))
                step_order += 1
            steps.append(
                {
                    "type": "RepeatGroupDTO",
                    "stepOrder": group_order,
                    "stepType": STEP_TYPES["repeat"],
                    "childStepId": child_step_id,
                    "numberOfIterations": sets,
                    "smartRepeat": False,
                    "endCondition": END_CONDITIONS["iterations"],
                    "endConditionValue": float(sets),
                    "workoutSteps": inner,
                }
            )
            child_step_id += 1
        else:
            steps.append(_exercise_step(step_order, None, exercise))
            step_order += 1
            if rest:
                steps.append(_rest_step(step_order, None, int(rest)))
                step_order += 1

    return {
        "sportType": SPORT_TYPE_STRENGTH,
        "subSportType": None,
        "workoutName": name,
        "description": description or None,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": SPORT_TYPE_STRENGTH,
                "workoutSteps": steps,
            }
        ],
        "avgTrainingSpeed": None,
        "estimatedDurationInSecs": 0,
        "estimatedDistanceInMeters": None,
        "estimateType": None,
    }


def _parse_json_arg(raw: Any, label: str) -> Any:
    """Tool args arrive as JSON strings from some clients and native types from others."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"{label} is not valid JSON: {e}") from e
    return raw


def _workout_id(upload_response: Any) -> Optional[int]:
    if isinstance(upload_response, dict):
        return upload_response.get("workoutId")
    return None


def register_tools(app):
    """Register all strength training authoring tools with the MCP server app"""

    @app.tool()
    async def create_strength_workout(
        name: str,
        exercises: str,
        description: str = "",
        schedule_date: str = "",
    ) -> str:
        """Create a weight training workout in Garmin Connect, optionally scheduling it.

        Args:
            name: Workout name as it will appear in Garmin Connect, e.g. "Upper Body A"
            exercises: JSON array of exercises. Each entry supports:
                exercise (required, e.g. "BARBELL_BACK_SQUAT"), category (optional,
                inferred when known), sets, reps, weight_kg, duration_seconds
                (for timed holds instead of reps), rest_seconds, notes.
                Example:
                [{"exercise": "BARBELL_BACK_SQUAT", "sets": 4, "reps": 5,
                  "weight_kg": 80, "rest_seconds": 150},
                 {"exercise": "PLANK", "sets": 3, "duration_seconds": 45,
                  "rest_seconds": 30}]
            description: Optional workout notes
            schedule_date: Optional date in YYYY-MM-DD format to put it on the calendar
        """
        try:
            spec = _parse_json_arg(exercises, "exercises")
            if not isinstance(spec, list):
                return "Error: 'exercises' must be a JSON array of exercise objects."

            payload = build_strength_workout(name, spec, description)
            response = garmin_client._client.upload_workout(payload)
            workout_id = _workout_id(response)
            if not workout_id:
                return f"Workout upload returned no workout ID. Response: {response}"

            result = f"Created strength workout '{name}' (workout ID {workout_id})."
            if schedule_date:
                garmin_client._client.schedule_workout(workout_id, schedule_date)
                result += f" Scheduled for {schedule_date}."
            return result
        except Exception as e:
            return f"Error creating strength workout: {str(e)}"

    @app.tool()
    async def create_strength_training_plan(plan: str) -> str:
        """Create and schedule a multi-session weight training plan in one call.

        Args:
            plan: JSON array of sessions. Each session supports:
                name (required), date (YYYY-MM-DD, schedules the session when given),
                description, and exercises (array, same format as create_strength_workout).
                Example:
                [{"name": "Week 1 - Lower", "date": "2026-07-27",
                  "exercises": [{"exercise": "BARBELL_BACK_SQUAT", "sets": 3,
                                 "reps": 5, "weight_kg": 80, "rest_seconds": 180}]}]
        """
        try:
            sessions = _parse_json_arg(plan, "plan")
            if not isinstance(sessions, list):
                return "Error: 'plan' must be a JSON array of session objects."

            created, failed = [], []
            for session in sessions:
                session_name = session.get("name", "Untitled session")
                try:
                    payload = build_strength_workout(
                        session_name,
                        session.get("exercises", []),
                        session.get("description", ""),
                    )
                    response = garmin_client._client.upload_workout(payload)
                    workout_id = _workout_id(response)
                    if not workout_id:
                        failed.append(f"{session_name}: upload returned no workout ID")
                        continue

                    line = f"{session_name} (ID {workout_id})"
                    date = session.get("date")
                    if date:
                        garmin_client._client.schedule_workout(workout_id, date)
                        line += f" scheduled {date}"
                    created.append(line)
                except Exception as e:
                    failed.append(f"{session_name}: {str(e)}")

            result = f"Created {len(created)} of {len(sessions)} sessions:\n"
            result += "\n".join(f"  - {line}" for line in created)
            if failed:
                result += "\n\nFailed:\n" + "\n".join(f"  - {line}" for line in failed)
            return result
        except Exception as e:
            return f"Error creating training plan: {str(e)}"

    @app.tool()
    async def schedule_workout(workout_id: int, date: str) -> str:
        """Put an existing workout on the Garmin training calendar.

        Args:
            workout_id: ID of the workout in the Garmin workout library
            date: Date in YYYY-MM-DD format
        """
        try:
            result = garmin_client._client.schedule_workout(workout_id, date)
            scheduled_id = (
                result.get("workoutScheduleId") if isinstance(result, dict) else None
            )
            return (
                f"Scheduled workout {workout_id} for {date}."
                + (f" Schedule ID {scheduled_id}." if scheduled_id else "")
            )
        except Exception as e:
            return f"Error scheduling workout: {str(e)}"

    @app.tool()
    async def unschedule_workout(scheduled_workout_id: int) -> str:
        """Remove a workout from the training calendar, keeping it in the library.

        Args:
            scheduled_workout_id: Schedule ID (not the workout ID) to remove
        """
        try:
            garmin_client._client.unschedule_workout(scheduled_workout_id)
            return f"Removed scheduled workout {scheduled_workout_id} from the calendar."
        except Exception as e:
            return f"Error unscheduling workout: {str(e)}"

    @app.tool()
    async def delete_workout(workout_id: int) -> str:
        """Delete a workout from the Garmin workout library.

        Args:
            workout_id: ID of the workout to delete
        """
        try:
            garmin_client._client.delete_workout(workout_id)
            return f"Deleted workout {workout_id}."
        except Exception as e:
            return f"Error deleting workout: {str(e)}"

    @app.tool()
    async def list_strength_exercises(search: str = "", category: str = "") -> str:
        """Look up Garmin exercise names to use in a workout.

        Garmin only accepts exercise names from its own catalogue, so use this
        to find the exact name before building a workout.

        Args:
            search: Filter on the name or its display text, e.g. "squat", "bench"
            category: Restrict to one category, e.g. "SQUAT", "DEADLIFT"
        """
        LIMIT = 120
        needle = search.strip().upper().replace(" ", "_").replace("-", "_")
        wanted = _normalise_exercise(category) if category else ""

        if wanted and wanted not in EXERCISES:
            return (
                f"Unknown category '{category}'. Categories: "
                + ", ".join(sorted(EXERCISES))
            )

        if not needle and not wanted:
            return (
                f"{sum(len(v) for v in EXERCISES.values())} exercises in "
                f"{len(EXERCISES)} categories. Search by name, or pass a category:\n"
                + "\n".join(
                    f"  {name} ({len(EXERCISES[name])})" for name in sorted(EXERCISES)
                )
            )

        matches: List[tuple] = []
        for cat in sorted(EXERCISES) if not wanted else [wanted]:
            for name, label in sorted(EXERCISES[cat].items()):
                haystack = f"{name}_{label.upper().replace(' ', '_')}"
                if not needle or needle in haystack:
                    matches.append((cat, name, label))

        if not matches:
            return f"No exercises matching '{search}'."

        lines = [f"{len(matches)} matches" + (f" (showing {LIMIT})" if len(matches) > LIMIT else "") + ":"]
        current = None
        for cat, name, label in matches[:LIMIT]:
            if cat != current:
                lines.append(f"\n{cat}:")
                current = cat
            lines.append(f"  {name}  ({label})")
        return "\n".join(lines)

    return app
