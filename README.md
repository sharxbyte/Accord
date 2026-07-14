# Concur Discord Bot 📚

Concur is an open-source Discord bot built with Python (`discord.py`) designed to inject structural clarity into active discussions, political debates, and casual conversations. By allowing individual users to declare their own contextual dictionary definitions, Concur parses channel messages in real-time to match defined keywords—offering contextual tools to help prevent semantic disputes before they stall a conversation.

🔒 **Designed with Compliance In Mind:** Concur strictly follows the Discord Developer Policy and California privacy standards (CCPA/CPRA). Message scanning occurs exclusively in-memory (volatile RAM) to dynamically evaluate keyword triggers and is immediately discarded. No personal user chats or logs are permanently written to a database.

---

## 🛠️ Features

* **Custom Definitions (`/def add`)**: Define personal words, acronyms, or specific phrases to reflect your exact meaning during a dispute.
* **Database Cooldown & Minimization**: Automatic database caching and transient memory cleanup prevent server strain and uphold data protection principles.
* **Official Dictionary Backups (`/define`)**: Integrates an external dictionary API lookup structure to fetch trustworthy, classical definitions on the fly.
* **User Control**: Individual definitions are fully managed, editable, and clearable instantly via interactive Discord slash commands.

---

## 🎮 Commands Lookup Table

All application commands are built as modern, interactive Slash Commands (`/`). Usage commands targeted by individuals return ephemeral responses only visible to the executing user to reduce channel clutter.

| Command Group | Command | Parameters | Visibility | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/def` | `add` | `[keyword]` `[definition]` | Ephemeral | Saves or modifies a custom phrase mapping linked to your Discord User ID. |
| `/def` | `remove` | `[keyword]` | Ephemeral | Permanently removes a custom phrase definition from your personal library storage. |
| `/def` | `view` | *None* | Ephemeral | Displays a cleanly formatted, paginated collection of your active saved definitions. |
| `/def` | `clear_all` | *None* | Ephemeral | Wipes your entire definition index profile completely out of the database. |
| *None* | `/define` | `[word]` | Ephemeral | Connects to an external official dictionary database API to retrieve accurate parts of speech and standard word descriptions. |

---

## 🚀 Technical Requirements & Stack

* **Language**: Python 3.8+
* **Core Libraries**: `discord.py`, `aiohttp`, `python-dotenv`
* **Database**: Embedded SQLite (`definitions.db`)
* **Hosting Support**: Fully configured for plug-and-play deployment on virtual environments or panels like Wispbyte.

---

## 💾 Installation & Local Setup

1. **Clone the Repository:**
   ```bash
   git clone [https://github.com/sharxbyte/Accord.git](https://github.com/sharxbyte/Accord.git)
   cd Accord
