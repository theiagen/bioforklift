from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import requests
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class SlackNotifier:
    """Sends notifications to Slack"""

    def __init__(self, token: str, channel_id: str):
        """
        Initialize Slack notification client

        Args:
            token: Slack API token
            channel_id: Slack channel ID to send messages to
        """
        self.token = token
        self.channel = channel_id

        if not self.token or not self.channel:
            raise ValueError("Slack token and channel ID must be provided")

    def send_message(self, message: str) -> Dict[str, Any]:
        """
        Send a simple message to Slack

        Args:
            message: The message to send

        Returns:
            Dictionary with Slack API response
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }

            payload = {"channel": self.channel, "text": message}

            response = requests.post(
                "https://slack.com/api/chat.postMessage", headers=headers, json=payload
            )

            result = response.json()
            if result.get("ok"):
                logger.info(f"Slack notification sent: {result.get('ts')}")
                return result
            else:
                logger.error(f"Slack API error: {result.get('error')}")
                raise Exception(f"Slack API error: {result.get('error')}")

        except Exception as exc:
            logger.error(f"Failed to send Slack notification: {str(exc)}")
            raise

    def send_formatted_message(
        self,
        title: str,
        message: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a formatted message to Slack

        Args:
            title: The title of the message
            message: The main message content
            attachments: Optional list of attachment dictionaries with keys like 'title', 'text', 'color'

        Returns:
            Dictionary with Slack API response
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }

            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": title}},
                {"type": "section", "text": {"type": "mrkdwn", "text": message}},
            ]

            # Add divider before attachments
            if attachments:
                blocks.append({"type": "divider"})

            # Convert attachments to blocks
            for attachment in attachments or []:
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{attachment.get('title', '')}*\n{attachment.get('text', '')}",
                        },
                    }
                )

            payload = {"channel": self.channel, "text": title, "blocks": blocks}

            response = requests.post(
                "https://slack.com/api/chat.postMessage", headers=headers, json=payload
            )

            result = response.json()
            if result.get("ok"):
                logger.info(f"Formatted Slack notification sent: {result.get('ts')}")
                return result
            else:
                logger.error(f"Slack API error: {result.get('error')}")
                raise Exception(f"Slack API error: {result.get('error')}")

        except Exception as exc:
            logger.error(f"Failed to send formatted Slack notification: {str(exc)}")
            raise


class TerraSummary:
    """Generate summaries of Terra operations for notifications"""

    def __init__(self, terra2bq):
        """
        Initialize Terra Summary

        Args:
            terra2bq: Terra2BQ instance to generate summaries from
        """
        self.terra2bq = terra2bq

    def generate_hourly_summary(
        self, hours_back: int = 1, config_name_column: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a summary of Terra operations for the last X hours

        Args:
            hours_back: Number of hours to look back

        Returns:
            Dictionary with summary information
        """
        # Use the timeframe functionality from Terra2BQ to get samples from the last hour
        samples_df = self.terra2bq.samples_ops.get_samples_by_timeframe(
            timeframe="custom",
            hours_back=hours_back,
            uploaded_filter="all",
            submitted_filter="all",
        )

        current_time = datetime.now(timezone.utc)
        start_time = current_time - timedelta(hours=hours_back)

        if samples_df.empty:
            return {
                "total_samples": 0,
                "uploaded_samples": 0,
                "submitted_samples": 0,
                "by_entity_type": [],
                "by_config": [],
                "start_time": start_time.isoformat(),
                "end_time": current_time.isoformat(),
            }

        # Get counts for uploaded and submitted samples
        uploaded_count = samples_df["uploaded_at"].notna().sum()
        submitted_count = samples_df["submitted_at"].notna().sum()

        # Group by entity type
        by_entity_type = []
        sample_identifier_field = (
            self.terra2bq.samples_ops.get_sample_identifier_field()
        )

        if "entity_type" in samples_df.columns:
            for entity_type, group in samples_df.groupby("entity_type"):
                sample_ids = []
                if (
                    sample_identifier_field
                    and sample_identifier_field in samples_df.columns
                ):
                    sample_ids = group[sample_identifier_field].tolist()

                by_entity_type.append(
                    {
                        "entity_type": entity_type,
                        "sample_count": len(group),
                        "sample_ids": sample_ids,
                    }
                )

        # Group by configuration
        config_id_field = self.terra2bq.samples_ops.get_config_identifier_field()
        display_name_field = self.terra2bq.config_ops.get_alerts_display_field()

        by_config = []
        if config_id_field and config_id_field in samples_df.columns:
            for config_id, group in samples_df.groupby(config_id_field):
                config = None
                if self.terra2bq.config_ops:
                    config = self.terra2bq.config_ops.get_config(config_id)

                if config_name_column:
                    config_name = config[config_name_column]
                elif display_name_field:
                    config_name = config[display_name_field]
                else:
                    config_name = f"Config {config_id}"

                entity_types = []
                if "entity_type" in group.columns:
                    entity_types = group["entity_type"].unique().tolist()

                by_config.append(
                    {
                        "config_id": config_id,
                        "config_name": config_name,
                        "total_samples": len(group),
                        "uploaded_samples": group["uploaded_at"].notna().sum(),
                        "submitted_samples": group["submitted_at"].notna().sum(),
                        "entity_types": entity_types,
                    }
                )

        return {
            "total_samples": len(samples_df),
            "uploaded_samples": uploaded_count,
            "submitted_samples": submitted_count,
            "by_entity_type": by_entity_type,
            "by_config": by_config,
            "start_time": start_time.isoformat(),
            "end_time": current_time.isoformat(),
        }

    def generate_daily_summary(
        self, config_name_column: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a summary of today's Terra operations

        Returns:
            Dictionary with summary information
        """
        # Use the timeframe functionality from Terra2BQ to get today's samples
        samples_df = self.terra2bq.samples_ops.get_samples_by_timeframe(
            timeframe="today", uploaded_filter="all", submitted_filter="all"
        )

        if samples_df.empty:
            return {
                "total_samples": 0,
                "uploaded_samples": 0,
                "submitted_samples": 0,
                "by_config": [],
                "date": datetime.now().strftime("%Y-%m-%d"),
            }

        # Get counts for uploaded and submitted samples
        uploaded_count = samples_df["uploaded_at"].notna().sum()
        submitted_count = samples_df["submitted_at"].notna().sum()

        # Group by configuration
        config_id_field = self.terra2bq.samples_ops.get_config_identifier_field()
        display_name_field = self.terra2bq.config_ops.get_alerts_display_field()

        by_config = []
        if config_id_field and config_id_field in samples_df.columns:
            for config_id, group in samples_df.groupby(config_id_field):
                config = None
                if self.terra2bq.config_ops:
                    config = self.terra2bq.config_ops.get_config(config_id)

                if config_name_column:
                    config_name = config[config_name_column]
                elif display_name_field:
                    config_name = config[display_name_field]
                else:
                    config_name = f"Config {config_id}"

                by_config.append(
                    {
                        "config_id": config_id,
                        "config_name": config_name,
                        "total_samples": len(group),
                        "uploaded_samples": group["uploaded_at"].notna().sum(),
                        "submitted_samples": group["submitted_at"].notna().sum(),
                        "entity_type": config.get("entity_type", "Unknown")
                        if config
                        else "Unknown",
                    }
                )

        return {
            "total_samples": len(samples_df),
            "uploaded_samples": uploaded_count,
            "submitted_samples": submitted_count,
            "by_config": by_config,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

    def generate_workflow_summary(self, days_back: int = 7) -> Dict[str, Any]:
        """
        Generate a summary of workflow states

        Args:
            days_back: Number of days to look back

        Returns:
            Dictionary with workflow summary information
        """
        if not self.terra2bq.config_ops:
            return {
                "error": "Config operations not initialized",
                "date": datetime.now().strftime("%Y-%m-%d"),
            }

        configs = self.terra2bq.get_active_configs()

        workflow_summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "days_back": days_back,
            "config_summaries": [],
        }

        total_states = {}

        for config in configs:
            try:
                config_id = config.get("id")
                state_summary = self.terra2bq.samples_ops.get_workflow_state_summary(
                    config_id
                )

                # Aggregate totals
                for state, count in state_summary.items():
                    if state not in total_states:
                        total_states[state] = 0
                    total_states[state] += count

                workflow_summary["config_summaries"].append(
                    {
                        "config_id": config_id,
                        "config_name": config.get("name", "Unknown"),
                        "states": state_summary,
                    }
                )
            except Exception as exc:
                logger.error(
                    f"Error generating workflow summary for config {config.get('id')}: {str(exc)}"
                )

        workflow_summary["total_states"] = total_states
        return workflow_summary

    def format_hourly_summary_for_slack(
        self, summary: Dict[str, Any], project_title: str = None
    ) -> Dict[str, Any]:
        """
        Format hourly summary for Slack message

        Args:
            summary: Summary data from generate_hourly_summary

        Returns:
            Dictionary with formatted title, message and attachments
        """
        # Format times for display
        start_time = summary.get("start_time", "")
        end_time = summary.get("end_time", "")

        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            time_range = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M %Z')}"
            date = start_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            time_range = "last hour"
            date = datetime.now().strftime("%Y-%m-%d")

        if project_title:
            title = f"{project_title} Hourly Summary ({date} {time_range})"
        else:
            title = f"Terra2BQ Hourly Summary ({date} {time_range})"

        message = f"*Summary of Terra operations for the past hour*\n"
        message += f"• Total samples: {summary['total_samples']}\n"
        message += f"• Uploaded to Terra: {summary['uploaded_samples']}\n"
        message += f"• Submitted to workflows: {summary['submitted_samples']}\n"

        attachments = []

        # Add entity type summary attachment
        if summary.get("by_entity_type"):
            entity_types_text = ""
            for entity in summary["by_entity_type"]:
                entity_types_text += (
                    f"• *{entity['entity_type']}*: {entity['sample_count']} samples\n"
                )

            attachments.append(
                {
                    "title": "Samples by Entity Type",
                    "text": entity_types_text,
                    "color": "#ECB22E",  # Slack yellow color
                }
            )

        # Add configuration summary attachments
        for config in summary.get("by_config", []):
            entity_types_str = ", ".join(config.get("entity_types", ["Unknown"]))

            attachment = {
                "title": f"{config['config_name']}",
                "text": (
                    f"• Entity Types: {entity_types_str}\n"
                    f"• Total samples: {config['total_samples']}\n"
                    f"• Uploaded to Terra: {config['uploaded_samples']}\n"
                    f"• Submitted to workflows: {config['submitted_samples']}"
                ),
                "color": "#36C5F0",
            }
            attachments.append(attachment)

        return {"title": title, "message": message, "attachments": attachments}

    def format_daily_summary_for_slack(
        self, summary: Dict[str, Any], project_title: str = None
    ) -> Dict[str, Any]:
        """
        Format daily summary for Slack message

        Args:
            summary: Summary data from generate_daily_summary

        Returns:
            Dictionary with formatted title, message and attachments
        """

        if project_title:
            title = f"{project_title} Daily Summary for {summary['date']}"
        else:
            title = f"Terra2BQ Daily Summary for {summary['date']}"

        message = f"*Summary of today's Terra operations*\n"
        message += f"• Total samples: {summary['total_samples']}\n"
        message += f"• Uploaded to Terra: {summary['uploaded_samples']}\n"
        message += f"• Submitted to workflows: {summary['submitted_samples']}\n"

        attachments = []

        for config in summary["by_config"]:
            attachment = {
                "title": f"{config['config_name']} ({config['entity_type']})",
                "text": (
                    f"• Total samples: {config['total_samples']}\n"
                    f"• Uploaded to Terra: {config['uploaded_samples']}\n"
                    f"• Submitted to workflows: {config['submitted_samples']}"
                ),
                "color": "#36C5F0",
            }
            attachments.append(attachment)

        return {"title": title, "message": message, "attachments": attachments}

    def format_workflow_summary_for_slack(
        self, summary: Dict[str, Any], project_title: str = None
    ) -> Dict[str, Any]:
        """
        Format workflow summary for Slack message

        Args:
            summary: Summary data from generate_workflow_summary

        Returns:
            Dictionary with formatted title, message and attachments
        """

        if project_title:
            title = (
                f"{project_title} Workflow Summary (Last {summary['days_back']} Days)"
            )
        else:
            title = f"Terra2BQ Workflow Summary (Last {summary['days_back']} Days)"

        message = "*Workflow State Summary*\n"

        # Format total states
        total_states = summary.get("total_states", {})
        if total_states:
            message += "*Overall Workflow States:*\n"
            for state, count in total_states.items():
                message += f"• {state}: {count}\n"

        attachments = []

        for config in summary.get("config_summaries", []):
            states_text = ""
            for state, count in config.get("states", {}).items():
                states_text += f"• {state}: {count}\n"

            attachment = {
                "title": config["config_name"],
                "text": states_text if states_text else "No workflow states found",
                "color": "#2EB67D",  # Slack green color
            }
            attachments.append(attachment)

        return {"title": title, "message": message, "attachments": attachments}


class SlackAlert:
    """Class for sending Terra alerts to Slack"""

    def __init__(self, notifier: SlackNotifier):
        """
        Initialize the SlackAlert system

        Args:
            notifier: SlackNotifier instance
        """
        self.notifier = notifier

    def send_message(self, message: str) -> Dict[str, Any]:
        """
        Send a simple message to Slack

        Args:
            message: Message to send

        Returns:
            Response dictionary from Slack
        """
        try:
            return self.notifier.send_message(message)
        except Exception as exc:
            logger.error(f"Error sending message to Slack: {str(exc)}")
            return {"error": str(exc)}

    def send_formatted_message(
        self,
        title: str,
        message: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a formatted message to Slack

        Args:
            title: Title of the message
            message: Message content
            attachments: Optional list of attachments

        Returns:
            Response dictionary from Slack
        """
        try:
            return self.notifier.send_formatted_message(title, message, attachments)
        except Exception as exc:
            logger.error(f"Error sending formatted message to Slack: {str(exc)}")
            return {"error": str(exc)}

    def send_hourly_summary(
        self, terra2bq_instance, project_title: str = None, hours_back: int = 1
    ) -> Dict[str, Any]:
        """
        Generate and send an hourly summary for a Terra2BQ instance

        Args:
            terra2bq_instance: Terra2BQ instance to generate summary for
            project_title: Title of the project for display
            hours_back: Number of hours to look back

        Returns:
            Response dictionary from Slack
        """
        summary = TerraSummary(terra2bq_instance).generate_hourly_summary(hours_back)

        # Skip sending if no samples were found
        if summary["total_samples"] == 0:
            logger.info(
                f"No samples found in the last {hours_back} hour(s). Skipping Slack notification."
            )
            return {"status": "skipped", "reason": "no_samples"}

        formatted = TerraSummary(terra2bq_instance).format_hourly_summary_for_slack(
            summary, project_title
        )

        return self.send_formatted_message(
            formatted["title"], formatted["message"], formatted["attachments"]
        )

    def send_daily_summary(
        self, terra2bq_instance, project_title: str = None
    ) -> Dict[str, Any]:
        """
        Generate and send a daily summary for a Terra2BQ instance

        Args:
            terra2bq_instance: Terra2BQ instance to generate summary for

        Returns:
            Response dictionary from Slack
        """
        summary = TerraSummary(terra2bq_instance).generate_daily_summary()
        formatted = TerraSummary(terra2bq_instance).format_daily_summary_for_slack(
            summary, project_title
        )

        return self.send_formatted_message(
            formatted["title"], formatted["message"], formatted["attachments"]
        )

    def send_workflow_summary(
        self, terra2bq_instance, project_title: str = None, days_back: int = 7
    ) -> Dict[str, Any]:
        """
        Generate and send a workflow summary for a Terra2BQ instance

        Args:
            terra2bq_instance: Terra2BQ instance to generate summary for
            days_back: Number of days to look back

        Returns:
            Response dictionary from Slack
        """
        summary = TerraSummary(terra2bq_instance).generate_workflow_summary(days_back)
        formatted = TerraSummary(terra2bq_instance).format_workflow_summary_for_slack(
            summary, project_title
        )

        return self.send_formatted_message(
            formatted["title"], formatted["message"], formatted["attachments"]
        )
