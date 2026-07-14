import os
import re
import time
import sqlite3
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional, Tuple, Dict, Any, List

# --- Global Setup and Constants ---
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DB_NAME = "definitions.db"

intents = discord.Intents.default()
intents.message_content = True  # Required for message parsing
intents.guilds = True

# Initialize Discord Bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Global state management for the parser cache and cooldowns
USER_COOLDOWNS: Dict[int, float] = {}
# Format: { channel_id: { user_id: { alias_lowercase: (timestamp, first_bot_msg_jump_url) } } }
DEFINITION_CACHE: Dict[int, Dict[int, Dict[str, Tuple[float, str]]]] = {}

# --- Database Manager ---

class DatabaseManager:
    """Handles all SQLite operations cleanly."""

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.setup_db()

    def _execute(self, query: str, params: tuple = None) -> list:
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            conn.commit()
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            raise e
        finally:
            conn.close()

    def setup_db(self):
        """Initializes the database schema."""
        query = """
        CREATE TABLE IF NOT EXISTS definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            guild_id TEXT, -- NULL for global definitions
            word_aliases TEXT NOT NULL,
            definition TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
        except sqlite3.Error as e:
            print(f"Failed to set up database: {e}")
        finally:
            conn.close()

    def get_total_definitions_count(self, user_id: str) -> int:
        """Returns the total number of definitions defined by a user."""
        query = "SELECT COUNT(*) FROM definitions WHERE user_id = ?"
        res = self._execute(query, (user_id,))
        return res[0][0] if res else 0

    def add_definition(self, user_id: str, guild_id: Optional[str], aliases: str, definition: str) -> bool:
        """Adds a new definition, enforcing constraints."""
        try:
            query = """
            INSERT INTO definitions (user_id, guild_id, word_aliases, definition)
            VALUES (?, ?, ?, ?)
            """
            self._execute(query, (user_id, guild_id, aliases, definition))
            return True
        except Exception as e:
            print(f"Failed to add definition: {e}")
            return False

    def get_definitions_for_parsing(self, user_id: str, guild_id: Optional[str]) -> list:
        """Retrieves all definitions for a user. Prioritizes server-specific entries."""
        # Query global entries
        global_res = self._execute("SELECT id, word_aliases, definition FROM definitions WHERE user_id=? AND guild_id IS NULL", (user_id,))
        # Query server-specific entries
        server_res = []
        if guild_id:
            server_res = self._execute("SELECT id, word_aliases, definition FROM definitions WHERE user_id=? AND guild_id=?", (user_id, str(guild_id)))
        
        # Format results
        all_defs = []
        for r in global_res:
            all_defs.append({"id": r[0], "guild_id": None, "word_aliases": r[1], "definition": r[2]})
        for r in server_res:
            all_defs.append({"id": r[0], "guild_id": str(guild_id), "word_aliases": r[1], "definition": r[2]})
            
        return all_defs

    def update_definition(self, user_id: str, guild_id: Optional[str], word: str, new_definition: str) -> bool:
        """Updates an existing definition containing the exact matched alias."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            # Fetch all definitions for this scope to find which row contains the alias
            if guild_id:
                cursor.execute("SELECT id, word_aliases FROM definitions WHERE user_id = ? AND guild_id = ?", (user_id, str(guild_id)))
            else:
                cursor.execute("SELECT id, word_aliases FROM definitions WHERE user_id = ? AND guild_id IS NULL", (user_id,))
            
            rows = cursor.fetchall()
            target_id = None
            for row_id, aliases_str in rows:
                aliases_list = [a.strip().lower() for a in aliases_str.split(',') if a.strip()]
                if word.strip().lower() in aliases_list:
                    target_id = row_id
                    break
            
            if target_id is None:
                return False

            cursor.execute("UPDATE definitions SET definition = ? WHERE id = ?", (new_definition, target_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_definition(self, user_id: str, guild_id: Optional[str], word: str) -> bool:
        """Deletes a definition matching the exact alias."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            if guild_id:
                cursor.execute("SELECT id, word_aliases FROM definitions WHERE user_id = ? AND guild_id = ?", (user_id, str(guild_id)))
            else:
                cursor.execute("SELECT id, word_aliases FROM definitions WHERE user_id = ? AND guild_id IS NULL", (user_id,))
            
            rows = cursor.fetchall()
            target_id = None
            for row_id, aliases_str in rows:
                aliases_list = [a.strip().lower() for a in aliases_str.split(',') if a.strip()]
                if word.strip().lower() in aliases_list:
                    target_id = row_id
                    break
            
            if target_id is None:
                return False

            cursor.execute("DELETE FROM definitions WHERE id = ?", (target_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_all_definitions_for_user(self, user_id: str) -> list:
        """Retrieves all definitions belonging to a user across all scopes."""
        results = self._execute("SELECT guild_id, word_aliases, definition FROM definitions WHERE user_id=?", (user_id,))
        out = []
        for r in results:
            out.append({
                "source": "Global Scope" if r[0] is None else f"Server Specific (ID: {r[0]})",
                "word_aliases": r[1],
                "definition": r[2]
            })
        return out

db = DatabaseManager(DB_NAME)

# --- Utility Functions ---

async def cooldown_check(interaction: discord.Interaction) -> bool:
    """Enforces a 5-second command cooldown."""
    user_id = interaction.user.id
    current_time = time.monotonic()
    cooldown_period = 5.0

    if user_id in USER_COOLDOWNS and USER_COOLDOWNS[user_id] > current_time:
        remaining_time = USER_COOLDOWNS[user_id] - current_time
        await interaction.response.send_message(
            f"⏳ Please wait before using this command. You must wait {int(remaining_time) + 1} seconds.", ephemeral=True
        )
        return False

    USER_COOLDOWNS[user_id] = current_time + cooldown_period
    return True

# --- Message Parsing Logic ---

async def parse_message(message: discord.Message):
    """Analyzes message content for custom definitions with exact-case prioritization and aliases."""
    if message.author.bot or not message.content or not message.guild:
        return

    guild_id = message.guild.id
    channel_id = message.channel.id
    user_id = message.author.id

    # Fetch user definitions
    definitions = db.get_definitions_for_parsing(str(user_id), str(guild_id))
    if not definitions:
        return

    # To implement "Server-specific overrides global", separate them
    server_defs = [d for d in definitions if d["guild_id"] is not None]
    global_defs = [d for d in definitions if d["guild_id"] is None]

    # Process server-specific matches first, then fall back to global
    all_active_definitions = server_defs + global_defs

    # Extract all aliases and map them back to their respective definitions
    # Structure: { alias_string: {"definition": str, "is_server_specific": bool} }
    alias_map: Dict[str, Dict[str, Any]] = {}
    for item in all_active_definitions:
        aliases = [a.strip() for a in item["word_aliases"].split(",") if a.strip()]
        for alias in aliases:
            # If the alias is already mapped, prioritize server-specific records over global
            if alias not in alias_map:
                alias_map[alias] = {
                    "definition": item["definition"],
                    "is_server_specific": item["guild_id"] is not None
                }

    if not alias_map:
        return

    # Search the text using regular expressions with word boundaries
    found_matches: List[Tuple[str, str]] = []  # List of (matched_alias_exactly, definition)

    # 1. First Pass: Look for Exact-case matches
    for alias, data in alias_map.items():
        pattern = rf"\b{re.escape(alias)}\b"
        if re.search(pattern, message.content):
            found_matches.append((alias, data["definition"]))

    # 2. Second Pass: If no exact match is found, do Case-Insensitive matching fallback
    if not found_matches:
        for alias, data in alias_map.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, message.content, re.IGNORECASE):
                found_matches.append((alias, data["definition"]))

    if not found_matches:
        return

    # Grab the first match found to prevent massive spam cascades
    matched_alias, definition = found_matches[0]
    matched_alias_lower = matched_alias.lower()

    # Cache handling setup
    if channel_id not in DEFINITION_CACHE:
        DEFINITION_CACHE[channel_id] = {}
    if user_id not in DEFINITION_CACHE[channel_id]:
        DEFINITION_CACHE[channel_id][user_id] = {}

    user_channel_cache = DEFINITION_CACHE[channel_id][user_id]
    current_time = time.time()
    one_hour = 3600

    # Scenario B: Definition was posted in this channel within 1 hour -> Send small link-back message
    if matched_alias_lower in user_channel_cache and (current_time - user_channel_cache[matched_alias_lower][0]) < one_hour:
        _, jump_url = user_channel_cache[matched_alias_lower]
        embed = discord.Embed(
            description=f"ℹ️ **{message.author.display_name}** is using their custom definition of *{matched_alias}* (defined [here]({jump_url})).",
            color=discord.Color.blue()
        )
        await message.channel.send(embed=embed)
    
    # Scenario A: First time posting word in 1 hour -> Send rich full definition
    else:
        embed = discord.Embed(
            title=f"📚 Custom Definition for `{matched_alias}`",
            description=definition,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Defined by {message.author.display_name}")
        sent_msg = await message.channel.send(embed=embed)

        # Cache the timestamp and jump URL of this rich embed reply
        user_channel_cache[matched_alias_lower] = (current_time, sent_msg.jump_url)


# --- Slash Commands and Group ---

class DefinitionGroup(app_commands.Group, name="def"):
    """All Slash commands grouped under /def"""
    pass

# Instantiate command tree group
def_group = DefinitionGroup()

@def_group.command(name="add", description="Adds a custom definition for words/phrases (aliases comma-separated).")
@app_commands.describe(
    words_or_aliases="Aliases (e.g. state, states, State). Max 100 chars.",
    definition="Definition text. Max 300 chars.",
    server_only="If True, only applies in this server. Default is False (Global)."
)
async def add_def(interaction: discord.Interaction, words_or_aliases: str, definition: str, server_only: bool = False):
    if not await cooldown_check(interaction):
        return

    try:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id) if (server_only and interaction.guild) else None

        # Clean inputs
        words_or_aliases = words_or_aliases.strip()
        definition = definition.strip()

        # Constraints validation
        if not words_or_aliases or not definition:
            raise ValueError("Aliases and definitions cannot be empty.")
        if len(words_or_aliases) > 100:
            raise ValueError("The alias list length cannot exceed 100 characters.")
        if len(definition) > 300:
            raise ValueError("The definition length cannot exceed 300 characters.")

        # Cap limit safeguard (Max 50 total definitions per user)
        if db.get_total_definitions_count(user_id) >= 50:
            raise ValueError("You have reached the maximum limit of 50 custom definitions.")

        if db.add_definition(user_id, guild_id, words_or_aliases, definition):
            scope_str = "Server Only" if server_only else "Global"
            await interaction.response.send_message(
                f"✅ Successfully added definitions for `{words_or_aliases}`! Scope: **{scope_str}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Failed to add definition.", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ **Error:** {str(e)}\n*Type `/help_def` to see how to use this command correctly.*",
            ephemeral=True
        )

@def_group.command(name="edit", description="Updates a definition matching one of your custom aliases.")
async def edit_def(interaction: discord.Interaction, word: str, new_definition: str):
    if not await cooldown_check(interaction):
        return

    try:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id) if interaction.guild else None
        new_definition = new_definition.strip()

        if len(new_definition) > 300:
            raise ValueError("The definition length cannot exceed 300 characters.")

        # Try server-specific scope first
        success = db.update_definition(user_id, guild_id, word, new_definition)
        
        # If not found, check global scope
        if not success and guild_id:
            success = db.update_definition(user_id, None, word, new_definition)

        if success:
            await interaction.response.send_message(f"✏️ Successfully updated the definition containing `{word}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Could not find a definition containing the alias `{word}` to update.", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ **Error:** {str(e)}\n*Type `/help_def` to see how to use this command correctly.*",
            ephemeral=True
        )

@def_group.command(name="remove", description="Removes a custom definition matching one of your custom aliases.")
async def remove_def(interaction: discord.Interaction, word: str):
    if not await cooldown_check(interaction):
        return

    try:
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id) if interaction.guild else None

        # Try server-specific delete first
        success = db.delete_definition(user_id, guild_id, word)

        # Try global delete fallback
        if not success and guild_id:
            success = db.delete_definition(user_id, None, word)

        if success:
            await interaction.response.send_message(f"🗑️ Successfully removed the definition containing the alias `{word}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Could not find a definition containing the alias `{word}` to delete.", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ **Error:** {str(e)}\n*Type `/help_def` to see how to use this command correctly.*",
            ephemeral=True
        )

@def_group.command(name="list", description="Lists all your defined words and aliases.")
async def list_def(interaction: discord.Interaction):
    if not await cooldown_check(interaction):
        return

    try:
        user_id = str(interaction.user.id)
        all_defs = db.get_all_definitions_for_user(user_id)

        if not all_defs:
            await interaction.response.send_message("ℹ️ You have not created any custom definitions yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📜 Your Custom Definitions",
            color=discord.Color.green()
        )
        
        description = ""
        for i, def_item in enumerate(all_defs):
            aliases_clean = def_item['word_aliases'].replace(',', '`, `')
            description += f"\n**{i+1}. Scope:** `{def_item['source']}`\n> **Aliases:** `{aliases_clean}`\n> **Definition:** {def_item['definition']}\n"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ **Error:** {str(e)}", ephemeral=True)

@def_group.command(name="view", description="Publicly inspect another server member's custom definitions.")
async def view_def(interaction: discord.Interaction, member: discord.Member):
    if not await cooldown_check(interaction):
        return

    try:
        target_id = str(member.id)
        all_defs = db.get_all_definitions_for_user(target_id)

        if not all_defs:
            await interaction.response.send_message(f"ℹ️ {member.mention} has not configured any custom definitions.", ephemeral=False)
            return

        embed = discord.Embed(
            title=f"📜 Definitions for {member.display_name}",
            color=discord.Color.dark_teal()
        )

        description = ""
        for i, def_item in enumerate(all_defs):
            aliases_clean = def_item['word_aliases'].replace(',', '`, `')
            description += f"\n**{i+1}. Scope:** `{def_item['source']}`\n> **Aliases:** `{aliases_clean}`\n> **Definition:** {def_item['definition']}\n"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ **Error:** {str(e)}", ephemeral=True)


# --- Root Level Slash Commands (Standalones) ---

@bot.tree.command(name="help_def", description="Explains all dictionary bot commands and features.")
async def help_def(interaction: discord.Interaction):
    """Stand-alone /help_def command."""
    embed = discord.Embed(
        title="📚 Custom Dictionary Bot Guide",
        description="This bot monitors and prints rich definition popups when you speak custom-defined words in chat.",
        color=discord.Color.blue()
    )

    rules = (
        "• **Global Scope:** Default behaviour. Definitions apply across all servers.\n"
        "• **Server Specific:** Pass `server_only: True` during add. This overrides global definitions inside this specific guild.\n"
        "• **Disambiguation / Case:** Matches exact casing first. Falls back to case-insensitive matching. "
        "Allows separate definitions for 'State' (political entity) and 'state' (state of matter).\n"
        "• **Aliases:** Use comma-separation for variants (e.g. `/def add words_or_aliases: democracy, democratic`)\n"
        "• **Spam Prevention:** Only 1 full rich definition is allowed per user/channel per hour. Repeat matches get a small hyperlink back."
    )
    embed.add_field(name="⚙️ General Rules & Scope Priority", value=rules, inline=False)

    cmds = (
        "📖 **/help_def** - Displays this layout guide.\n\n"
        "➕ **/def add [aliases] [definition] [server_only]** - Adds a definition. Max 50 per user.\n\n"
        "✏️ **/def edit [alias] [new_definition]** - Edits a definition mapping containing the given alias.\n\n"
        "🗑️ **/def remove [alias]** - Deletes a definition mapping.\n\n"
        "📋 **/def list** - Privately lists your definitions.\n\n"
        "👀 **/def view [user]** - Publicly views another user's dictionary.\n\n"
        "🌐 **/define [word]** - Fallback query to fetch dictionary definition using an external API."
    )
    embed.add_field(name="💬 Available Commands", value=cmds, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="define", description="Look up a standard word definition from an external dictionary.")
async def define_external(interaction: discord.Interaction, word: str):
    if not await cooldown_check(interaction):
        return

    await interaction.response.defer(ephemeral=True)
    api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as response:
                if response.status == 404:
                    await interaction.followup.send(
                        f"⚠️ Could not find a dictionary entry for `{word}`. *Type `/help_def` for helper options.*", 
                        ephemeral=True
                    )
                    return

                data = await response.json()

        definition_text = "Definition unavailable."
        if isinstance(data, list) and data:
            meanings = data[0].get('meanings', [])
            if meanings:
                first_meaning = meanings[0]
                part_of_speech = first_meaning.get('partOfSpeech', 'N/A')
                definitions_list = first_meaning.get('definitions', [])
                
                if definitions_list:
                    raw_def = definitions_list[0].get('definition', 'No description found.')
                    definition_text = f"**Part of Speech:** {part_of_speech}\n\n*Description:* {raw_def}"

        embed = discord.Embed(
            title=f"📚 Dictionary Lookup: `{word}`",
            description=definition_text,
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred connecting to external resources: {str(e)}", ephemeral=True)


# --- Event Listeners ---

@bot.event
async def on_ready():
    print('----------------------------------------')
    # Add Group command tree safely
    bot.tree.add_command(def_group)
    
    # Sync Commands Globally
    await bot.tree.sync()
    
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('SQLite database is connected and ready.')
    print('----------------------------------------')

@bot.event
async def on_message(message: discord.Message):
    # Pass off message parsing to our utility module logic
    await parse_message(message)
    await bot.process_commands(message)


# --- Run Bot ---

if __name__ == "__main__":
    if not TOKEN:
        print("Fatal Error: DISCORD_BOT_TOKEN environment variable not found.")
    else:
        bot.run(TOKEN)