# First, install required packages:
# pip install discord.py[voice] yt-dlp python-dotenv

import os
import asyncio
import discord
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv


# Load environment variables
load_dotenv()
TOKEN = "TOKEN"

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# YouTube DL options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# FFMPEG options
FFMPEG_OPTIONS = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

# Create YT DLP client
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class MusicBot:
    def __init__(self):
        self.queue = []
        self.is_playing = False
        self.current_song = None
        self.voice_client = None

    async def join_voice_channel(self, ctx):
        if ctx.author.voice is None:
            await ctx.send("You're not connected to a voice channel!")
            return False
        
        voice_channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            self.voice_client = await voice_channel.connect()
        else:
            await ctx.voice_client.move_to(voice_channel)
            self.voice_client = ctx.voice_client
        return True

    def play_next(self, ctx):
        if len(self.queue) > 0 and self.voice_client:
            self.is_playing = True
            url = self.queue.pop(0)
            
            def after_playing(error):
                if error:
                    print(f'Player error: {error}')
                if len(self.queue) > 0:
                    self.play_next(ctx)
                else:
                    self.is_playing = False

            # Get audio source
            loop = asyncio.get_event_loop()
            data = loop.run_until_complete(self.get_audio_source(url))
            if data:
                self.voice_client.play(discord.FFmpegPCMAudio(
                    data['url'], **FFMPEG_OPTIONS), after=after_playing)

    async def get_audio_source(self, url):
        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False))
            if 'entries' in data:  # It's a playlist
                data = data['entries'][0]
            return data
        except Exception as e:
            print(f"Error extracting info: {e}")
            return None

music_bot = MusicBot()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command(name='play')
async def play(ctx, url):
    """Play a song from YouTube URL"""
    # Connect to voice channel
    if ctx.author.voice is None:
        await ctx.send("You're not connected to a voice channel!")
        return
    
    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await voice_channel.connect()
    
    # Get the audio
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        
        if 'entries' in data:  # It's a playlist
            url2 = data['entries'][0]['url']
        else:
            url2 = data['url']
        
        # Play the audio
        source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
        ctx.voice_client.play(source)
        
        await ctx.send(f'Now playing: {data.get("title", "Unknown title")}')
        
    except Exception as e:
        print(f"Error details: {str(e)}")  # This will show in your console
        await ctx.send(f'An error occurred while trying to play the audio: {str(e)}')

@bot.command(name='stop')
async def stop(ctx):
    """Stop playing and clear the queue"""
    if ctx.voice_client:
        music_bot.queue = []
        ctx.voice_client.stop()
        await ctx.send('Stopped playing and cleared the queue')

@bot.command(name='skip')
async def skip(ctx):
    """Skip the current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send('Skipped the current song')
        music_bot.play_next(ctx)

@bot.command(name='leave')
async def leave(ctx):
    """Leave the voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        music_bot.queue = []
        music_bot.is_playing = False
        await ctx.send('Left the voice channel')

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)