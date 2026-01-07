"""
Webex Bot Application - Flask webhook handler for Pipeline Notify.

This module handles incoming Webex webhooks, processes messages and card actions,
and dispatches commands to the MCP orchestrator.
"""

import os
import logging
import hmac
import hashlib
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from webexteamssdk import WebexTeamsAPI

from bot.handlers.commands import CommandHandler
from bot.handlers.cards import CardHandler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize Webex API
webex_token = os.getenv("WEBEX_BOT_TOKEN")
if not webex_token:
    raise RuntimeError("WEBEX_BOT_TOKEN not set in environment")

webex_api = WebexTeamsAPI(access_token=webex_token)
bot_email = os.getenv("WEBEX_BOT_EMAIL", webex_api.people.me().emails[0])

# Initialize handlers
command_handler = CommandHandler(webex_api)
card_handler = CardHandler(webex_api)

# Webhook secret for verification
webhook_secret = os.getenv("WEBEX_WEBHOOK_SECRET", "")


def verify_webhook_signature(request_data: bytes, signature: str) -> bool:
    """Verify the webhook signature from Webex."""
    if not webhook_secret:
        logger.warning("WEBEX_WEBHOOK_SECRET not set - skipping signature verification")
        return True
    
    expected = hmac.new(
        webhook_secret.encode(),
        request_data,
        hashlib.sha1
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "pipeline-notify-bot"})


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Handle incoming Webex webhooks.
    
    Processes:
    - messages/created: New message from user
    - attachmentActions/created: Card submission (dropdown selection)
    """
    # Verify signature if secret is set
    signature = request.headers.get("X-Spark-Signature", "")
    if webhook_secret and not verify_webhook_signature(request.data, signature):
        logger.warning("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    data = request.json
    resource = data.get("resource")
    event = data.get("event")
    
    logger.info(f"Received webhook: {resource}/{event}")
    
    try:
        if resource == "messages" and event == "created":
            # Handle new message
            message_id = data.get("data", {}).get("id")
            if message_id:
                message = webex_api.messages.get(message_id)
                
                # Ignore messages from the bot itself
                if message.personEmail == bot_email:
                    return jsonify({"status": "ignored", "reason": "self-message"})
                
                # Process the command
                response = command_handler.handle_message(message)
                return jsonify({"status": "processed", "response": response})
        
        elif resource == "attachmentActions" and event == "created":
            # Handle card action (dropdown selection, button click)
            action_id = data.get("data", {}).get("id")
            if action_id:
                action = webex_api.attachment_actions.get(action_id)
                response = card_handler.handle_action(action)
                return jsonify({"status": "processed", "response": response})
        
        return jsonify({"status": "unhandled", "resource": resource, "event": event})
    
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/webhooks/setup", methods=["POST"])
def setup_webhooks():
    """
    Setup or update Webex webhooks.
    
    Call this endpoint to register the bot's webhooks with Webex.
    Requires 'target_url' in the request body.
    """
    data = request.json or {}
    target_url = data.get("target_url")
    
    if not target_url:
        return jsonify({"error": "target_url required"}), 400
    
    try:
        # Delete existing webhooks
        existing = webex_api.webhooks.list()
        for webhook in existing:
            webex_api.webhooks.delete(webhook.id)
            logger.info(f"Deleted webhook: {webhook.name}")
        
        # Create new webhooks
        webhooks_created = []
        
        # Messages webhook
        msg_webhook = webex_api.webhooks.create(
            name="Pipeline Notify - Messages",
            targetUrl=f"{target_url}/webhook",
            resource="messages",
            event="created",
            secret=webhook_secret if webhook_secret else None
        )
        webhooks_created.append({"name": msg_webhook.name, "id": msg_webhook.id})
        
        # Attachment actions webhook (for cards)
        card_webhook = webex_api.webhooks.create(
            name="Pipeline Notify - Card Actions",
            targetUrl=f"{target_url}/webhook",
            resource="attachmentActions",
            event="created",
            secret=webhook_secret if webhook_secret else None
        )
        webhooks_created.append({"name": card_webhook.name, "id": card_webhook.id})
        
        return jsonify({
            "status": "success",
            "webhooks": webhooks_created
        })
    
    except Exception as e:
        logger.exception(f"Error setting up webhooks: {e}")
        return jsonify({"error": str(e)}), 500


def main():
    """Run the Flask application."""
    port = int(os.getenv("BOT_PORT", 5000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting Pipeline Notify Bot on port {port}")
    logger.info(f"Bot email: {bot_email}")
    
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
