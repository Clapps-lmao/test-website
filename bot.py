import discord
from discord.ext import commands
from discord import Interaction, app_commands
from discord.ui import Select, View
import random
import aiosqlite
import datetime
import re
from discord.ui import View, Select, Modal, TextInput, Button
from datetime import timedelta
import uuid
from typing import Optional

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synchronized.")

# Initialize bot
bot = MyBot()

DB_FILE = "database/bot_data.db"

# Initialize database

async def initialize_database():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, account TEXT NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, expiration TEXT NOT NULL, user_id INTEGER, duration TEXT NOT NULL, cooldown INTEGER NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS generated_stats (user_id INTEGER PRIMARY KEY, generated_count INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS admin_users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS admin_roles (role_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS blacklisted_users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS platforms (platform TEXT PRIMARY KEY)")
        await db.commit()

async def is_admin(interaction: Interaction) -> bool:
    """Checks if the user is an admin based on recognized roles or user IDs."""
    user_id = interaction.user.id
    roles = [role.id for role in interaction.user.roles]

    async with aiosqlite.connect(DB_FILE) as db:
        # Check if the user is explicitly an admin
        async with db.execute("SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                return True

        # Check if the user has any recognized admin role
        async with db.execute("SELECT role_id FROM admin_roles") as cursor:
            recognized_roles = [row[0] for row in await cursor.fetchall()]
            if any(role in recognized_roles for role in roles):
                return True

    return False

async def admin_only(interaction: Interaction):
    """Restricts command access to admins."""
    if not await is_admin(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        raise Exception("Unauthorized access attempt.")

@bot.event
async def on_ready():
    await initialize_database()
    print(f"Logged in as {bot.user}")
    activity = discord.Streaming(name="Coded By Clapps", url="https://beziic.wtf")
    await bot.change_presence(status=discord.Status.dnd, activity=activity)

@bot.tree.command(name="platform-create", description="Create a new platform (Admin only).")
@app_commands.describe(platform="Name of the platform to add.")
async def platform_create(interaction: Interaction, platform: str):
    await admin_only(interaction)
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(description="You don't have permission to use this command.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    async with aiosqlite.connect(DB_FILE) as db:
        try:
            await db.execute("INSERT INTO platforms (platform) VALUES (?)", (platform,))
            await db.commit()
            embed = discord.Embed(description=f"Platform `{platform}` has been added successfully.", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        except aiosqlite.IntegrityError:
            embed = discord.Embed(description=f"Platform `{platform}` already exists.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

class PlatformSelect(Select):
    def __init__(self, platforms, callback):
        options = [
            discord.SelectOption(label=platform, value=platform) for platform in platforms
        ]
        super().__init__(placeholder="Select a platform...", options=options, custom_id="platform_select")
        self.callback = callback

class PlatformView(View):
    def __init__(self, platforms, callback):
        super().__init__()
        self.add_item(PlatformSelect(platforms, callback))

@bot.tree.command(name="bulk_add", description="Adds multiple accounts from an uploaded .txt file.")
@app_commands.describe(file="Text file containing accounts, one per line.")
async def bulk_add(interaction: Interaction, file: discord.Attachment):
    await admin_only(interaction)
    if not file.filename.endswith('.txt'):
        embed = discord.Embed(description="Invalid file type. Please upload a .txt file.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        file_content = await file.read()
        accounts_list = file_content.decode('utf-8').splitlines()
    except Exception as e:
        embed = discord.Embed(description="Failed to read the file. Please try again.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        print(f"Error reading file: {e}")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT platform FROM platforms") as cursor:
            platforms = [row[0] for row in await cursor.fetchall()]
            if not platforms:
                embed = discord.Embed(description="No platforms available. Please add platforms first.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

    async def handle_selection(interaction: Interaction):
        selected_platform = interaction.data['values'][0]
        async with aiosqlite.connect(DB_FILE) as db:
            await db.executemany(
                "INSERT INTO accounts (platform, account) VALUES (?, ?)",
                [(selected_platform, account) for account in accounts_list]
            )
            await db.commit()

        embed = discord.Embed(description=f"Added {len(accounts_list)} accounts to {selected_platform}.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)

    view = PlatformView(platforms, handle_selection)
    embed = discord.Embed(description="Please select the platform to add accounts.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="add_account", description="Adds a single account to the generator.")
@app_commands.describe(platform="Platform name", account="Account in user:pass format.")
async def add_account(interaction: Interaction, platform: str, account: str):
    await admin_only(interaction)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO accounts (platform, account) VALUES (?, ?)", (platform, account))
        await db.commit()
    embed = discord.Embed(description=f"Account added to {platform}: {account}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="View generator statistics.")
async def stats(interaction: Interaction):
    user_id = interaction.user.id

    async with aiosqlite.connect(DB_FILE) as db:
        # Get the total number of accounts in the generator
        async with db.execute("SELECT COUNT(*) FROM accounts") as cursor:
            total_accounts = await cursor.fetchone()
            total_accounts = total_accounts[0] if total_accounts else 0

        # Get the number of accounts generated by the user
        async with db.execute("SELECT generated_count FROM generated_stats WHERE user_id = ?", (user_id,)) as cursor:
            user_generated_count = await cursor.fetchone()
            user_generated_count = user_generated_count[0] if user_generated_count else 0
        # Fetch number of accounts per platform
        async with db.execute("SELECT platform, COUNT(*) FROM accounts GROUP BY platform") as cursor:
            platform_stats = await cursor.fetchall()

        # Format platform stats for display
        platform_stats_message = "\n".join(
            [f"🔹 {platform}: {count}" for platform, count in platform_stats]
        ) if platform_stats else "No accounts available on any platform."

    # Create the stats message
    stats_message = (
        f"📊 **Generator Statistics** 📊\n\n"
        f"🔹 Total Accounts in Generator: **{total_accounts}**\n"
        f"🔹 Accounts Generated by You: **{user_generated_count}**\n\n"
        f"**Accounts by Platform:**\n{platform_stats_message}\n\n"
        f"Thank you for using this generator! 😊"
    )

    await interaction.response.send_message(stats_message, ephemeral=True)

def parse_duration(duration: str) -> timedelta | None:
    """
    Parses a duration string into a timedelta object. Returns None for 'lifetime'.
    Supports units: 'y', 'mo', 'w', 'd', 'h', 'm'.

    Args:
        duration (str): The duration string to parse (e.g., '1y 2mo 3w 4d 5h 6m').

    Returns:
        timedelta | None: A timedelta object representing the parsed duration or None for 'lifetime'.
    """
    if duration.strip().lower() == "lifetime":
        return None  # Special case for lifetime keys

    # Regex to capture duration (e.g., '1y', '2mo', etc.)
    pattern = r"(?:(\d+)\s*y)?\s*(?:(\d+)\s*mo)?\s*(?:(\d+)\s*w)?\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?"
    match = re.fullmatch(pattern, duration.strip().lower())
    
    if not match:
        raise ValueError("Invalid duration format. Use combinations of 'y', 'mo', 'w', 'd', 'h', 'm'.")

    # Extract matches and convert to integers (default to 0 if None)
    years = int(match.group(1)) if match.group(1) else 0
    months = int(match.group(2)) if match.group(2) else 0
    weeks = int(match.group(3)) if match.group(3) else 0
    days = int(match.group(4)) if match.group(4) else 0
    hours = int(match.group(5)) if match.group(5) else 0
    minutes = int(match.group(6)) if match.group(6) else 0

    # Convert everything to approximate timedelta
    total_days = years * 365 + months * 30 + weeks * 7 + days
    return timedelta(days=total_days, hours=hours, minutes=minutes)


class DurationDropdown(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 Hour", value="1h"),
            discord.SelectOption(label="1 Day", value="1d"),
            discord.SelectOption(label="1 Week", value="1w"),
            discord.SelectOption(label="1 Month", value="1mo"),
            discord.SelectOption(label="1 Year", value="1y"),
            discord.SelectOption(label="Lifetime", value="lifetime"),
        ]
        super().__init__(
            placeholder="Select a duration",
            options=options,
            custom_id="duration_dropdown"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_duration = self.values[0]
        # Open cooldown input modal after duration is selected
        await interaction.response.send_modal(CooldownInputModal(selected_duration))

class CooldownInputModal(Modal):
    def __init__(self, duration):
        super().__init__(title="Set Cooldown")
        self.duration = duration
        self.cooldown_input = TextInput(
            label="Cooldown (in seconds)",
            placeholder="Enter a cooldown period (e.g., 3600 for 1 hour)",
            required=True
        )
        self.add_item(self.cooldown_input)

    async def on_submit(self, interaction: discord.Interaction):
        cooldown = int(self.cooldown_input.value)
        try:
            expiration_timedelta = parse_duration(self.duration)
            if expiration_timedelta is None:  # 'lifetime' case
                expiration = None
            else:
                expiration = datetime.datetime.now() + expiration_timedelta
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        # Generate a key starting with BEZIICPREM-
        key = 'BEZIICPREM-' + ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890', k=10))

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT INTO keys (key, expiration, cooldown, user_id) VALUES (?, ?, ?, NULL)", 
                             (key, expiration, cooldown))
            await db.commit()

        expiration_message = "Lifetime" if expiration is None else f"Expires in: {expiration_timedelta}"
        embed = discord.Embed(
            description=(
                f"Generated key: `{key}`\n"
                f"{expiration_message}\n"
                f"Cooldown: {cooldown} seconds"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

class GenerateKeyView(View):
    def __init__(self):
        super().__init__()
        self.add_item(DurationDropdown())

@bot.tree.command(name="generate_key", description="Generate an activation key with dropdown options.")
async def generate_key_command(interaction: discord.Interaction):
    await admin_only(interaction)
    view = GenerateKeyView()
    await interaction.response.send_message(
        "Select the duration for the activation key:", 
        view=view, 
        ephemeral=True
    )


@bot.tree.command(name="activate", description="Activates a key.")
@app_commands.describe(key="The activation key.")
async def activate(interaction: Interaction, key: str):
    user_id = interaction.user.id

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT expiration, user_id FROM keys WHERE key = ?", (key,)) as cursor:
            key_data = await cursor.fetchone()
            
            if not key_data:
                await interaction.response.send_message("Invalid key!", ephemeral=True)
                return

            expiration, assigned_user_id = key_data
            
            # Check if the key is lifetime or expired
            if expiration:
                expiration_date = datetime.datetime.fromisoformat(expiration)
                if datetime.datetime.now() > expiration_date:
                    await interaction.response.send_message("This key has expired!", ephemeral=True)
                    return
            else:
                # Lifetime key handling (no expiration date to check)
                expiration_date = None

            # Check if the key is already assigned
            if assigned_user_id is not None:
                await interaction.response.send_message("This key has already been activated!", ephemeral=True)
                return

        # Update the key's assigned user
        await db.execute("UPDATE keys SET user_id = ? WHERE key = ?", (user_id, key))
        await db.commit()

    # Inform the user of successful activation
    if expiration_date:
        await interaction.response.send_message(
            f"Key activated successfully! Expires on: {expiration_date.strftime('%Y-%m-%d %H:%M:%S')}. You can now use /generate.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "Key activated successfully with lifetime access! You can now use /generate.",
            ephemeral=True,
        )


async def handle_account_generation(interaction: Interaction, selected_platform: str):
    user_id = interaction.user.id

    async with aiosqlite.connect(DB_FILE) as db:
        # Fetch one account for the selected platform
        async with db.execute(
            "SELECT account FROM accounts WHERE platform = ? LIMIT 1",
            (selected_platform,)
        ) as cursor:
            account_data = await cursor.fetchone()
            if not account_data:
                await interaction.response.send_message(
                    f"No accounts available for the platform '{selected_platform}'.",
                    ephemeral=True,
                )
                return

            account = account_data[0]

        # Delete the fetched account
        async with db.execute(
            "DELETE FROM accounts WHERE platform = ? AND account = ?",
            (selected_platform, account)
        ):
            await db.commit()

        # Update user-generated statistics
        async with db.execute(
            "SELECT generated_count FROM generated_stats WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            user_stats = await cursor.fetchone()
            if user_stats:
                await db.execute(
                    "UPDATE generated_stats SET generated_count = generated_count + 1 WHERE user_id = ?",
                    (user_id,)
                )
            else:
                await db.execute(
                    "INSERT INTO generated_stats (user_id, generated_count) VALUES (?, 1)",
                    (user_id,)
                )
            await db.commit()

    await interaction.response.send_message(
        f"Here is your generated account for {selected_platform}: `{account}`",
        ephemeral=True,
    )

@bot.tree.command(name="generate", description="Generate an account.")
async def generate(interaction: Interaction):
    user_id = interaction.user.id

    async with aiosqlite.connect(DB_FILE) as db:
        # Fetch available platforms for the dropdown
        async with db.execute("SELECT DISTINCT platform FROM accounts") as cursor:
            platforms = await cursor.fetchall()

        if not platforms:
            await interaction.response.send_message("No platforms are available.", ephemeral=True)
            return

        platform_options = [
            discord.SelectOption(label=platform[0]) for platform in platforms
        ]

        # Dropdown for selecting the platform
        class PlatformDropdown(Select):
            def __init__(self):
                super().__init__(
                    placeholder="Select a platform",
                    min_values=1,
                    max_values=1,
                    options=platform_options,
                )

            async def callback(self, platform_interaction: Interaction):
                selected_platform = self.values[0]

                # Check if the user has an active key
                async with aiosqlite.connect(DB_FILE) as db_check:
                    async with db_check.execute(
                        "SELECT expiration FROM keys WHERE user_id = ?", (user_id,)
                    ) as cursor:
                        key_data = await cursor.fetchone()
                        if not key_data:
                            await platform_interaction.response.send_message(
                                "You don't have an active key! Activate a key first.", ephemeral=True
                            )
                            return

                        expiration = key_data[0]
                        if expiration and datetime.datetime.now() > datetime.datetime.fromisoformat(expiration):
                            await platform_interaction.response.send_message(
                                "Your key has expired! Activate a new key to continue.", ephemeral=True
                            )
                            return

                # Delegate account generation to the shared handler
                await handle_account_generation(platform_interaction, selected_platform)

        view = View()
        view.add_item(PlatformDropdown())
        await interaction.response.send_message("Please select a platform:", view=view, ephemeral=True)

@bot.tree.command(name="key_info", description="Check key information.")
@app_commands.describe(key="The key to check information for (optional).")
async def key_info(interaction: Interaction, key: str = None):
    user_id = interaction.user.id

    async with aiosqlite.connect(DB_FILE) as db:
        if key:
            # Fetch information about the provided key
            async with db.execute("SELECT key, expiration, cooldown, user_id FROM keys WHERE key = ?", (key,)) as cursor:
                key_data = await cursor.fetchone()
                if not key_data:
                    await interaction.response.send_message("The specified key does not exist.", ephemeral=True)
                    return
        else:
            # Fetch information about the key assigned to the user
            async with db.execute("SELECT key, expiration, cooldown, user_id FROM keys WHERE user_id = ?", (user_id,)) as cursor:
                key_data = await cursor.fetchone()
                if not key_data:
                    await interaction.response.send_message("You do not have an active key.", ephemeral=True)
                    return

        # Extract key information
        key_value, expiration, cooldown, owner_id = key_data

        # Format expiration date
        if expiration:
            expiration_datetime = datetime.datetime.fromisoformat(expiration)
            expiration_str = expiration_datetime.strftime("%m/%d/%y %H:%M")
        else:
            expiration_str = "Lifetime"

        owner_info = "Unassigned" if not owner_id else f"<@{owner_id}>"

        # Create the embed
        embed = discord.Embed(
            title="🔑 Key Information",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Key", value=f"`{key_value}`", inline=False)
        embed.add_field(name="Expiration", value=f"`{expiration_str}`", inline=False)
        embed.add_field(name="Cooldown", value=f"`{cooldown or 'None'}` seconds", inline=False)
        embed.add_field(name="Assigned To", value=owner_info, inline=False)
        embed.set_footer(text="Key Information Requested")

        # Send the embed
        await interaction.response.send_message(embed=embed, ephemeral=True)
	
@bot.tree.command(name="admin_user", description="Grants admin privileges to a user.")
@app_commands.describe(user="The user to be granted admin privileges.")
async def admin_user(interaction: Interaction, user: discord.User):
    await admin_only(interaction)

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO admin_users (user_id) VALUES (?)", (user.id,))
        await db.commit()

    await interaction.response.send_message(f"{user.mention} has been added as an admin.", ephemeral=True)

@bot.tree.command(name="admin_role", description="Grants admin privileges to a role.")
@app_commands.describe(role="The role to be granted admin privileges.")
async def admin_role(interaction: Interaction, role: discord.Role):
    await admin_only(interaction)

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO admin_roles (role_id) VALUES (?)", (role.id,))
        await db.commit()

    await interaction.response.send_message(f"{role.name} has been added as an admin role.", ephemeral=True)
	
@bot.tree.command(name="blacklist", description="Bans a user from using the generator.")
@app_commands.describe(user="The user to blacklist.")
async def blacklist(interaction: Interaction, user: discord.User):
    await admin_only(interaction)
    user_id = user.id

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id FROM blacklist WHERE user_id = ?", (user_id,)) as cursor:
            data = await cursor.fetchone()
        
        if data:
            await db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await db.commit()
            await interaction.response.send_message(f"{user.name} has been removed from the blacklist.")
        else:
            await db.execute("INSERT INTO blacklist (user_id) VALUES (?)", (user_id,))
            await db.commit()
            await interaction.response.send_message(f"{user.name} has been added to the blacklist.")

@bot.tree.command(name="remove_blacklist", description="Removes a user from the blacklist.")
@app_commands.describe(user="The user to remove from the blacklist.")
async def remove_blacklist(interaction: Interaction, user: discord.User):
    await admin_only(interaction)
    user_id = user.id

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id FROM blacklist WHERE user_id = ?", (user_id,)) as cursor:
            data = await cursor.fetchone()
        
        if data:
            await db.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            await db.commit()
            await interaction.response.send_message(f"{user.name} has been removed from the blacklist.")
        else:
            await interaction.response.send_message(f"{user.name} is not in the blacklist.")

@bot.tree.command(name="key-addtime", description="Add time to an existing key or make it lifetime.")
async def key_addtime(interaction: discord.Interaction, amount: str, key: str):
    """
    Add time to an existing key or convert it to lifetime.

    :param interaction: The interaction instance
    :param amount: The amount of time to add (e.g., 1s, 1m, 1h, 1d, 1mo, 1y, or 'lifetime')
    :param key: The key to which time will be added
    """
    # Ensure the user has permissions (optional, you can implement role checks here)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Handle "lifetime" conversion
    if amount.lower() == "lifetime":
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT expiration FROM keys WHERE key = ?", (key,)) as cursor:
                key_data = await cursor.fetchone()

            if not key_data:
                await interaction.response.send_message(
                    "Key not found. Please provide a valid key.", ephemeral=True
                )
                return

            # Set expiration to None for lifetime
            await db.execute("UPDATE keys SET expiration = NULL WHERE key = ?", (key,))
            await db.commit()

        await interaction.response.send_message(
            f"The key `{key}` has been updated to lifetime validity.", ephemeral=True
        )
        return

    # Parse the time amount
    try:
        time_value = int(amount[:-1])  # Extract the numeric part
        time_unit = amount[-1].lower()  # Extract the unit (s, m, h, d, mo, y)
    except (ValueError, IndexError):
        await interaction.response.send_message(
            "Invalid time format. Use formats like `1s`, `1m`, `1h`, `1d`, `1mo`, `1y`, or 'lifetime'.", ephemeral=True
        )
        return

    # Convert the time amount into seconds
    if time_unit == "s":
        delta = datetime.timedelta(seconds=time_value)
    elif time_unit == "m":
        delta = datetime.timedelta(minutes=time_value)
    elif time_unit == "h":
        delta = datetime.timedelta(hours=time_value)
    elif time_unit == "d":
        delta = datetime.timedelta(days=time_value)
    elif time_unit == "mo":
        delta = datetime.timedelta(days=time_value * 30)  # Approximate 1 month as 30 days
    elif time_unit == "y":
        delta = datetime.timedelta(days=time_value * 365)  # Approximate 1 year as 365 days
    else:
        await interaction.response.send_message(
            "Invalid time unit. Use `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `mo` (months), or `y` (years).", ephemeral=True
        )
        return

    # Update the key in the database
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT expiration FROM keys WHERE key = ?", (key,)) as cursor:
            key_data = await cursor.fetchone()

        if not key_data:
            await interaction.response.send_message(
                "Key not found. Please provide a valid key.", ephemeral=True
            )
            return

        current_expiration = key_data[0]
        if current_expiration:
            new_expiration = datetime.datetime.fromisoformat(current_expiration) + delta
        else:
            new_expiration = datetime.datetime.now() + delta

        # Update the key's expiration
        await db.execute(
            "UPDATE keys SET expiration = ? WHERE key = ?",
            (new_expiration.isoformat(), key),
        )
        await db.commit()

    # Send confirmation
    await interaction.response.send_message(
        f"Successfully added {amount} to the key `{key}`.\nNew expiration date: {new_expiration.strftime('%Y-%m-%d %H:%M:%S')}",
        ephemeral=True,
    )

@bot.tree.command(name="edit_cooldown", description="Edit the cooldown of a key.")
@app_commands.describe(key="The key to edit the cooldown for.", cooldown="The new cooldown in seconds.")
async def edit_cooldown(interaction: Interaction, key: str, cooldown: int):
    # Check if the user has admin permissions
    user_id = interaction.user.id
    user_roles = [role.id for role in interaction.user.roles] if interaction.guild else []

    async with aiosqlite.connect(DB_FILE) as db:
        # Verify if the user is an admin user or has an admin role
        async with db.execute("SELECT user_id FROM admin_users WHERE user_id = ?", (user_id,)) as cursor:
            is_admin_user = await cursor.fetchone()

        async with db.execute("SELECT role_id FROM admin_roles") as cursor:
            admin_roles = await cursor.fetchall()
            is_admin_role = any(role_id[0] in user_roles for role_id in admin_roles)

        if not is_admin_user and not is_admin_role:
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return

        # Check if the key exists
        async with db.execute("SELECT key FROM keys WHERE key = ?", (key,)) as cursor:
            key_exists = await cursor.fetchone()

        if not key_exists:
            await interaction.response.send_message("The specified key does not exist.", ephemeral=True)
            return

        # Update the cooldown for the key
        await db.execute("UPDATE keys SET cooldown = ? WHERE key = ?", (cooldown, key))
        await db.commit()

        # Send a success message
        embed = discord.Embed(
            title="🔄 Cooldown Updated",
            description=f"The cooldown for the key `{key}` has been updated to `{cooldown}` seconds.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Cooldown updated successfully.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="keys_viewall", description="View all existing keys.")
async def keys_viewall(interaction: Interaction):
    # Check if the user has admin permissions
    user_id = interaction.user.id
    user_roles = [role.id for role in interaction.user.roles] if interaction.guild else []

    async with aiosqlite.connect(DB_FILE) as db:
        # Verify if the user is an admin user or has an admin role
        async with db.execute("SELECT user_id FROM admin_users WHERE user_id = ?", (user_id,)) as cursor:
            is_admin_user = await cursor.fetchone()

        async with db.execute("SELECT role_id FROM admin_roles") as cursor:
            admin_roles = await cursor.fetchall()
            is_admin_role = any(role_id[0] in user_roles for role_id in admin_roles)

        if not is_admin_user and not is_admin_role:
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return

        # Fetch all keys
        async with db.execute("SELECT key, expiration, cooldown, user_id FROM keys") as cursor:
            keys = await cursor.fetchall()

    if not keys:
        await interaction.response.send_message("There are no keys available.", ephemeral=True)
        return

    # Pagination Logic
    keys_per_page = 10
    total_pages = (len(keys) + keys_per_page - 1) // keys_per_page

    def create_embed(page: int):
        embed = discord.Embed(
            title=f"🔑 All Keys (Page {page}/{total_pages})",
            description="List of all keys:",
            color=discord.Color.blue()
        )
        start_index = (page - 1) * keys_per_page
        end_index = start_index + keys_per_page
        for key, expiration, cooldown, user_id in keys[start_index:end_index]:
            expiration_str = "Never" if not expiration else datetime.datetime.fromisoformat(expiration).strftime("%m/%d/%y %H:%M")
            user_str = "Unassigned" if not user_id else f"<@{user_id}>"
            embed.add_field(
                name=f"Key: `{key}`",
                value=f"**Expiration:** {expiration_str}\n**Cooldown:** {cooldown} seconds\n**Assigned to:** {user_str}",
                inline=False
            )
        embed.set_footer(text="Use the buttons below to navigate pages.")
        return embed

    # Button View for Pagination
    class KeysView(View):
        def __init__(self):
            super().__init__()
            self.page = 1

        async def update_message(self, interaction: Interaction):
            embed = create_embed(self.page)
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
        async def previous_page(self, interaction: Interaction, button: Button):
            if self.page > 1:
                self.page -= 1
                await self.update_message(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
        async def next_page(self, interaction: Interaction, button: Button):
            if self.page < total_pages:
                self.page += 1
                await self.update_message(interaction)

    # Send initial embed and view
    embed = create_embed(1)
    view = KeysView()
    await interaction.response.send_message(embed=embed)

@bot.command(name="bulk-key-create")
async def bulk_key_create(ctx, amount: int, duration: str, cooldown: int):
    if amount <= 0:
        await ctx.send("Please specify a positive number of keys to generate.")
        return
    if cooldown < 0:
        await ctx.send("Cooldown must be a non-negative integer.")
        return

    # Parse the duration
    time_units = {
        's': 'seconds',
        'm': 'minutes',
        'h': 'hours',
        'd': 'days',
        'y': 'years'
    }

    try:
        unit = duration[-1]
        value = int(duration[:-1])
        if unit not in time_units:
            raise ValueError("Invalid duration unit.")
        if unit == 'y':
            expiration = datetime.utcnow() + timedelta(days=365 * value)
        else:
            kwargs = {time_units[unit]: value}
            expiration = datetime.utcnow() + timedelta(**kwargs)
    except (ValueError, TypeError):
        await ctx.send("Invalid duration format. Use formats like `1d`, `30m`, or `2y`.")
        return

    # Generate keys and insert them into the database
    new_keys = []
    async with aiosqlite.connect(DB_FILE) as db:
        for _ in range(amount):
            key = str(uuid.uuid4())  # Generate a random unique key
            await db.execute(
                "INSERT INTO keys (key, expiration, cooldown) VALUES (?, ?, ?)",
                (key, expiration.isoformat(), cooldown)
            )
            new_keys.append(key)
        await db.commit()

    # Display keys in an embed
    embed = discord.Embed(
        title="Bulk Key Creation",
        description=f"Successfully generated {amount} keys.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Duration", value=f"Valid for {duration}", inline=True)
    embed.add_field(name="Cooldown", value=f"{cooldown} seconds", inline=True)

    # Show up to 5 keys per field to keep the embed readable
    for i in range(0, len(new_keys), 5):
        keys_batch = "\n".join(new_keys[i:i + 5])
        embed.add_field(name="Keys", value=keys_batch, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="revoke-key")
async def revoke_key(ctx, key: str = None, user: discord.User = None):
    if not key and not user:
        await ctx.send("You must specify either a key or a user to revoke.")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        if key:
            # Revoke the specific key
            result = await db.execute("SELECT * FROM keys WHERE key = ?", (key,))
            key_data = await result.fetchone()

            if key_data:
                await db.execute("DELETE FROM keys WHERE key = ?", (key,))
                await db.commit()
                await ctx.send(f"The key `{key}` has been successfully revoked.")
            else:
                await ctx.send(f"The key `{key}` does not exist.")
        elif user:
            # Revoke all keys assigned to the user
            result = await db.execute("SELECT key FROM keys WHERE user_id = ?", (user.id,))
            keys_to_revoke = await result.fetchall()

            if keys_to_revoke:
                await db.execute("DELETE FROM keys WHERE user_id = ?", (user.id,))
                await db.commit()
                revoked_keys = ", ".join([key[0] for key in keys_to_revoke])
                await ctx.send(f"The following keys have been revoked from {user.mention}: {revoked_keys}")
            else:
                await ctx.send(f"No keys are currently assigned to {user.mention}.")


if __name__ == "__main__":
    # Load the bot token from a file or environment variable
    try:
        with open("config/token.txt", "r") as token_file:
            TOKEN = token_file.read().strip()
    except FileNotFoundError:
        print("Error: Token file not found. Please ensure 'config/token.txt' exists and contains the bot token.")
        exit(1)



    # Start the bot
    bot.run(TOKEN)
