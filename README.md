# 📚 Custom Dictionary Bot

A high-performance Discord bot designed to allow users within a server community to set, manage, and use custom definitions for words and phrases, with robust multi-server isolation logic.

## ✨ Features Overview

*   **Custom Definitions:** Define words/aliases (e.g., "State," "states") and their custom meanings.
*   **Multi-Scope Isolation:** Supports **Global** definitions (apply everywhere) and **Server-Specific** definitions (only applicable to the current server).
*   **Priority System:** Server-specific definitions always override global ones for that user.
*   **Advanced Matching:** Uses dynamic regex generation (`\b(word1|word2)\b`) ensuring word boundaries are respected, handling multi-aliases and case fallback efficiently.
*   **Message Parsing:** Detects custom words in chat messages. Displays a rich embed on first use (in 1 hour) and a simple link reply thereafter.
*   **External Lookup:** Integrates with an external dictionary API for standard definitions.

## 🚀 Getting Started

### Prerequisites
1. Python 3.8+
2. A Discord Bot Token (`DISCORD_BOT_TOKEN`). Ensure the bot has necessary permissions (Read Message History, Send Messages/Embeds, Administrator rights may be needed for viewing other users).
3. The `requirements.txt` dependencies installed.

### Installation
1. Clone or navigate to your project directory.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
