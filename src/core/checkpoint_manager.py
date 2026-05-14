"""
Checkpoint Manager — Sub-Agent State Persistence & Recovery

Enables resumable sub-agent execution with minimal overhead.
Writes STATE.json + MANIFEST.json every checkpoint interval.
Handles recovery from interruptions without data loss.

Usage:
    checkpointer = CheckpointManager(
        session_id="imagebot-hr-saas-2026-03-11-abc123",
        agent_name="imagebot",
        output_dir="/workspace/projects/orchestrator/agents/imagebot",
        total_tasks=15
    )
    
    for i in range(total_tasks):
        result = do_work(i)
        checkpointer.mark_complete(i, result)  # Auto-saves on interval
    
    checkpointer.finalize()  # Final state + manifest
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


class CheckpointManager:
    """Manages checkpoint state for resumable sub-agent execution."""

    def __init__(
        self,
        session_id: str,
        agent_name: str,
        output_dir: str,
        total_tasks: int,
        checkpoint_interval: int = 5,  # Write checkpoint every N tasks
    ):
        """
        Initialize checkpoint manager.

        Args:
            session_id: Unique session identifier (e.g., "imagebot-hr-saas-2026-03-11-abc123")
            agent_name: Agent type (e.g., "imagebot", "copybot", "x_sentiment_scorer")
            output_dir: Directory to write checkpoint files
            total_tasks: Total number of tasks to complete
            checkpoint_interval: Write checkpoint every N completed tasks
        """
        self.session_id = session_id
        self.agent_name = agent_name
        self.output_dir = Path(output_dir)
        self.total_tasks = total_tasks
        self.checkpoint_interval = checkpoint_interval

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State tracking
        self.start_time = datetime.utcnow()
        self.last_checkpoint_time = self.start_time
        self.completed_tasks: List[int] = []
        self.failed_tasks: List[int] = []
        self.outputs: Dict[int, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.total_cost = 0.0

    def mark_complete(
        self,
        task_index: int,
        output: Any,
        cost: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Mark a task as complete and optionally save checkpoint.

        Args:
            task_index: 0-based task index
            output: Task result/output
            cost: Cost incurred for this task (if applicable)
            metadata: Additional metadata for this task
        """
        self.completed_tasks.append(task_index)
        self.outputs[task_index] = output
        self.total_cost += cost

        if metadata:
            self.metadata[task_index] = metadata

        # Save checkpoint at interval
        if len(self.completed_tasks) % self.checkpoint_interval == 0:
            self.checkpoint()

    def mark_failed(self, task_index: int, error: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_index: 0-based task index
            error: Error message
        """
        self.failed_tasks.append(task_index)
        self.checkpoint()

    def checkpoint(self) -> None:
        """Write current state to STATE.json + MANIFEST.json."""
        state = self._build_state()
        manifest = self._build_manifest()

        # Write STATE.json
        state_file = self.output_dir / "STATE.json"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        # Write MANIFEST.json
        manifest_file = self.output_dir / "MANIFEST.json"
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        # Update SESSION_REGISTRY.json at workspace level
        self._update_session_registry(state)

        self.last_checkpoint_time = datetime.utcnow()

    def finalize(self) -> Dict[str, Any]:
        """
        Finalize execution and write final state.
        Call when all tasks complete or on shutdown.

        Returns:
            Final state dictionary
        """
        state = self._build_state()
        state["status"] = "complete" if len(self.failed_tasks) == 0 else "partial"
        state["completedAt"] = datetime.utcnow().isoformat() + "Z"

        manifest = self._build_manifest()
        manifest["finalized"] = True

        # Write final checkpoint
        state_file = self.output_dir / "STATE.json"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        manifest_file = self.output_dir / "MANIFEST.json"
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        # Write recovery instructions
        self._write_recovery_md(state)

        # Final registry update
        self._update_session_registry(state)

        return state

    def get_recovery_point(self) -> Dict[str, Any]:
        """
        Get information about where to resume from.
        Useful for error handlers or manual inspection.

        Returns:
            Dictionary with recovery details
        """
        next_index = len(self.completed_tasks) + len(self.failed_tasks)
        return {
            "sessionId": self.session_id,
            "canResume": True,
            "currentProgress": f"{len(self.completed_tasks)}/{self.total_tasks}",
            "nextTaskIndex": next_index,
            "failedTasks": self.failed_tasks,
            "totalCost": self.total_cost,
            "estimatedTimeRemaining": self._estimate_time_remaining(),
        }

    # Private methods

    def _build_state(self) -> Dict[str, Any]:
        """Build STATE.json content."""
        elapsed = datetime.utcnow() - self.start_time
        elapsed_seconds = elapsed.total_seconds()

        return {
            "sessionId": self.session_id,
            "agent": self.agent_name,
            "startedAt": self.start_time.isoformat() + "Z",
            "lastUpdatedAt": datetime.utcnow().isoformat() + "Z",
            "status": "in_progress",
            "progress": {
                "total": self.total_tasks,
                "completed": len(self.completed_tasks),
                "failed": len(self.failed_tasks),
                "pending": self.total_tasks - len(self.completed_tasks) - len(
                    self.failed_tasks
                ),
                "percentComplete": (
                    len(self.completed_tasks) / self.total_tasks * 100
                    if self.total_tasks > 0
                    else 0
                ),
            },
            "recovery": {
                "canResume": True,
                "resumePoint": f"Task {len(self.completed_tasks)} of {self.total_tasks}",
                "skipExisting": True,
                "estimatedTimeRemaining": self._estimate_time_remaining(),
            },
            "costs": {
                "totalCost": self.total_cost,
                "costPerTask": (
                    self.total_cost / len(self.completed_tasks)
                    if len(self.completed_tasks) > 0
                    else 0
                ),
            },
            "timing": {
                "elapsedSeconds": elapsed_seconds,
                "avgTimePerTask": (
                    elapsed_seconds / len(self.completed_tasks)
                    if len(self.completed_tasks) > 0
                    else 0
                ),
            },
        }

    def _build_manifest(self) -> Dict[str, Any]:
        """Build MANIFEST.json content."""
        return {
            "sessionId": self.session_id,
            "agent": self.agent_name,
            "outputs": {
                "completed": [
                    {
                        "taskIndex": i,
                        "output": self.outputs.get(i),
                        "metadata": self.metadata.get(i, {}),
                    }
                    for i in sorted(self.completed_tasks)
                ],
                "failed": self.failed_tasks,
            },
            "summary": {
                "totalGenerated": len(self.completed_tasks),
                "totalFailed": len(self.failed_tasks),
                "totalCost": f"${self.total_cost:.2f}",
                "allCompleted": len(self.completed_tasks) == self.total_tasks,
            },
        }

    def _write_recovery_md(self, state: Dict[str, Any]) -> None:
        """Write RECOVERY.md with human-readable recovery instructions."""
        progress = state["progress"]
        costs = state["costs"]

        recovery_md = f"""# Recovery Instructions for {self.agent_name}

## Current Status
- **Started:** {state["startedAt"]}
- **Last Update:** {state["lastUpdatedAt"]}
- **Progress:** {progress["completed"]}/{progress["total"]} tasks ({progress["percentComplete"]:.1f}%)
- **Status:** {state["status"]}

## What Was Done
✅ Completed: {progress["completed"]} tasks
❌ Failed: {progress["failed"]} tasks
⏳ Pending: {progress["pending"]} tasks

## Costs
- Total Cost: ${costs["totalCost"]:.2f}
- Cost Per Task: ${costs["costPerTask"]:.4f}

## Recovery Information

### If Resuming
- Resume Point: {state["recovery"]["resumePoint"]}
- Skip Completed: Yes (automatically resumed tasks won't be re-run)
- Estimated Time Remaining: {state["recovery"]["estimatedTimeRemaining"]}

### Session Registry
Session ID: `{self.session_id}`
Checkpoint: `/workspace/projects/orchestrator/agents/{self.agent_name}/STATE.json`
Manifest: `/workspace/projects/orchestrator/agents/{self.agent_name}/MANIFEST.json`

### Resume Command (Auto)
When resuming, provide these checkpoint files as attachments:
1. RECOVERY.md (this file)
2. MANIFEST.json (completed outputs)

The sub-agent will automatically detect the checkpoint and resume from Task {progress["completed"] + 1}.

### Manual Recovery
If automatic resume fails:
1. Inspect MANIFEST.json for completed outputs
2. Verify all output URLs/data are valid (spot-check 2-3)
3. If valid: proceed to next phase (don't regenerate)
4. If corrupted: restart from Task 1 (full regeneration necessary)
"""

        recovery_file = self.output_dir / "RECOVERY.md"
        with open(recovery_file, "w") as f:
            f.write(recovery_md)

    def _update_session_registry(self, state: Dict[str, Any]) -> None:
        """Update central SESSION_REGISTRY.json."""
        registry_file = (
            Path("/home/brad/.openclaw/workspace/projects/orchestrator/shared")
        )
        registry_file.mkdir(parents=True, exist_ok=True)

        registry_path = registry_file / "SESSION_REGISTRY.json"

        # Read existing registry or create new
        if registry_path.exists():
            with open(registry_path, "r") as f:
                registry = json.load(f)
        else:
            registry = {"sessions": []}

        # Find or create session entry
        session_entry = next(
            (s for s in registry["sessions"] if s["sessionId"] == self.session_id),
            None,
        )

        if not session_entry:
            session_entry = {
                "sessionId": self.session_id,
                "agent": self.agent_name,
                "status": state.get("status", "in_progress"),
                "startedAt": state.get("startedAt"),
                "lastUpdatedAt": state.get("lastUpdatedAt"),
                "canResume": state.get("recovery", {}).get("canResume", True),
                "checkpointFile": str(self.output_dir / "STATE.json"),
            }
            registry["sessions"].append(session_entry)
        else:
            session_entry["status"] = state.get("status", "in_progress")
            session_entry["lastUpdatedAt"] = state.get("lastUpdatedAt")
            session_entry["canResume"] = state.get("recovery", {}).get(
                "canResume", True
            )

        # Write updated registry
        with open(registry_path, "w") as f:
            json.dump(registry, f, indent=2)

    def _estimate_time_remaining(self) -> str:
        """Estimate time remaining based on current pace."""
        if len(self.completed_tasks) == 0:
            return "unknown"

        elapsed = datetime.utcnow() - self.start_time
        elapsed_seconds = elapsed.total_seconds()
        tasks_remaining = self.total_tasks - len(self.completed_tasks)

        if elapsed_seconds <= 0:
            return "calculating"

        avg_time_per_task = elapsed_seconds / len(self.completed_tasks)
        estimated_remaining_seconds = avg_time_per_task * tasks_remaining

        minutes = int(estimated_remaining_seconds / 60)
        seconds = int(estimated_remaining_seconds % 60)

        if minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
