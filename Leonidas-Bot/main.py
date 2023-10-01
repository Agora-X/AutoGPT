import aiohttp
import os
import discord
import asyncio
import subprocess
import pty
from discord import app_commands
import logging
from dotenv import load_dotenv
import uuid
from threading import Thread

load_dotenv('.env')

logging.basicConfig(level=logging.DEBUG)

DISCORD_BOT_SECRET = os.getenv('DISCORD_BOT_SECRET')
API_KEY = os.getenv('API_KEY')
headers = {"Authorization": API_KEY}
print(f"Bot token: {DISCORD_BOT_SECRET}")

class CustomClient(discord.Client):

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

# Function to generate a unique thread name or ID
def generate_thread_id():
    return str(uuid.uuid4())

client = CustomClient(intents=discord.Intents.all())

async def query(api_url, payload):
    print(f"Debug: Making request to {api_url} with payload: {payload}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, headers=headers, data=payload) as response:
                result = await response.json()
                print(f"Debug: Response from {api_url}: {result}")
                return result
        except Exception as e:
            print(f"Debug: Error during request to {api_url}: {str(e)}")
            return {"error": str(e)}

async def configure_env(interaction):
    # Determine the channel type (guild channel or DM)
    channel_type = interaction.channel.type

    # Create a function to send messages (compatible with both DMs and guild channels)
    async def send_message(message):
        if channel_type == discord.ChannelType.private:
            await interaction.user.send(message)
        else:
            await interaction.followup.send(message)

    await interaction.response.defer()

    # Prompt the user for the OpenAI API key
    await send_message("Please provide your OpenAI API key:")

    def remove_last_line_from_file(filename):
        with open(filename, 'r+') as file:
            lines = file.readlines()
            file.truncate(0)
            file.seek(0)
            for line in lines[:-1]: 
                file.write(line)

    def check_key_message(message):
        return message.author == interaction.user and message.channel == interaction.channel

    # Wait for the user's response
    key_message = await client.wait_for('message', check=check_key_message)
    openai_key = key_message.content

    # Generate a unique thread ID for the terminal thread
    terminal_thread_id = generate_thread_id()
    
    # Update the .env file in the specified directory
    env_file_path = '../autogpts/autogpt/.env'

    with open(env_file_path, 'a') as file:
        # Append the OpenAI API key and terminal thread ID
        file.write(f"OPENAI_API_KEY={openai_key}\n")
        file.write(f"TERMINAL_THREAD_ID={terminal_thread_id}\n")

    # Optionally, you can update the environment variables for the current process as well
    os.environ["OPENAI_API_KEY"] = openai_key
    os.environ["TERMINAL_THREAD_ID"] = terminal_thread_id

    await send_message("OpenAI API key and terminal thread ID have been set successfully!")

def run_docker_commands_in_terminal(interaction):
    # This function will run in a separate terminal thread for each summon command
    # Navigate to the specified directory
    os.chdir('../autogpts/autogptold/')

    # Build the Docker image
    build_process = subprocess.Popen(["docker-compose", "build", "auto-gpt"])
    build_process.wait()

    # Create a pseudo-terminal
    master, slave = pty.openpty()

    # Run the Docker container with the specified options
    run_process = subprocess.Popen(["docker-compose", "run", "-u", "root", "--rm", "auto-gpt", "--gpt4only", "--continuous"],
                                   stdin=slave, text=True)


    asyncio.sleep(10)

    os.write(master, b'n\n')

    interaction.followup.send('Please enter your goal:')
    try:
        response = client.wait_for('message', timeout=30.0, check=lambda message: message.author == interaction.user)
        goal_prompt = response.content
        # Send the user's input to the Docker process
        os.write(master, (goal_prompt + '\n').encode())

        # Continue with the rest of the code as needed
    except asyncio.TimeoutError:
        interaction.followup.send('You took too long to answer. Please try again.')

# Function to generate a unique Discord thread name or ID
def generate_discord_thread_id():
    return str(uuid.uuid4())

@client.event
async def on_ready():
    print("Bot is ready")

@client.tree.command(name="configure_env", description="Configure environment variables")
async def invoke_configure_env_command(interaction: discord.Interaction):
    await configure_env(interaction)

@client.tree.command(name="summon", description="Summon the AI to execute a specific task")
async def summon_command(interaction: discord.Interaction):
    await interaction.response.defer()
    await interaction.followup.send('Summoning the AI and executing the task, please wait...')
    
    # Create a new terminal thread to run the Docker commands
    terminal_thread = Thread(target=run_docker_commands_in_terminal, args=(interaction,))
    terminal_thread.start()
    
    # Generate a unique Discord thread ID for the temporary Discord thread
    discord_thread_id = generate_discord_thread_id()
    
    # Get the channel where the summon command was invoked
    channel = interaction.channel
    
    # Create a temporary Discord thread
    await channel.create_text_thread(name=f"Temporary Thread - {discord_thread_id}")
    
    await interaction.followup.send('Task completed successfully!')

client.run(DISCORD_BOT_SECRET)



