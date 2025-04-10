# main.py

# ===================== CONFIG =====================
TOKEN = "7517064569:AAETTbhQtkk-aXeZza1nGElFJxz9LzVgWYc"
# Supabase config
SUPABASE_URL = "https://xgxvgwbhtithacplqwet.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhneHZnd2JodGl0aGFjcGxxd2V0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQxNjYzMzIsImV4cCI6MjA1OTc0MjMzMn0.cu-Hid90BZK74GKWOa4IF5vR2owok9kmLChWrgz1ytM"

# ===================== IMPORT =====================
import logging
import asyncio
import random
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client

# ===================== DATABASE =====================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def create_giveaway(title, duration, num_winners, organizer):
    end_time = (datetime.now(timezone.utc) + timedelta(minutes=duration)).isoformat()
    data = {
        "title": title,
        "duration": duration,
        "num_winners": num_winners,
        "organizer": organizer,
        "end_time": end_time
    }
    result = supabase.table("giveaways").insert(data).execute()
    return result.data[0]["id"]

def get_expired_giveaways():
    now = datetime.now(timezone.utc).isoformat()
    result = supabase.table("giveaways").select("*").lte("end_time", now).execute()
    return result.data

def add_participant(giveaway_id, user_id, username):
    try:
        supabase.table("participants").insert({
            "giveaway_id": giveaway_id,
            "user_id": user_id,
            "username": username
        }).execute()
    except Exception:
        pass

def get_participants(giveaway_id):
    result = supabase.table("participants").select("username").eq("giveaway_id", giveaway_id).execute()
    return [row["username"] for row in result.data]

def delete_giveaway(giveaway_id):
    giveaway_id = int(giveaway_id)
    supabase.table("participants").delete().eq("giveaway_id", giveaway_id).execute()
    supabase.table("giveaways").delete().eq("id", giveaway_id).execute()

def set_post_channel(channel):
    supabase.table("settings").update({"post_channel": channel}).eq("id", 1).execute()

def get_post_channel():
    result = supabase.table("settings").select("post_channel").eq("id", 1).execute()
    return result.data[0]["post_channel"]

def add_required_channel(channel):
    current = get_required_channels()
    if channel not in current:
        current.append(channel)
        supabase.table("settings").update({"required_channels": current}).eq("id", 1).execute()

def remove_required_channel(channel):
    current = get_required_channels()
    if channel in current:
        current.remove(channel)
        supabase.table("settings").update({"required_channels": current}).eq("id", 1).execute()

def get_required_channels():
    result = supabase.table("settings").select("required_channels").eq("id", 1).execute()
    return result.data[0]["required_channels"]

# ===================== CHECK CHANNEL =====================
async def check_single_channel(bot, channel, user_id):
    try:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"❌ Error checking {channel}: {e}")
        return False

async def check_participation(user_id):
    try:
        bot = Bot(token=TOKEN)
        semaphore = asyncio.Semaphore(5)

        async def limited_check(channel):
            async with semaphore:
                return await check_single_channel(bot, channel, user_id)

        tasks = [limited_check(channel) for channel in get_required_channels()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        if any(isinstance(res, Exception) for res in results):
            print(f"⚠️ Error in check_participation: {results}")
            return False

        return all(results)
    except Exception as e:
        print(f"🔥 Fatal error in check_participation: {e}")
        return False

# ===================== BOT HANDLER =====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /newgiveaway to start a giveaway.")

async def new_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 4:
            await update.message.reply_text("Usage: /newgiveaway <prize_link> <duration> <num_winners> <organizer>")
            return

        title = args[0]
        duration = int(args[-3])
        num_winners = int(args[-2])
        organizer = args[-1]
        giveaway_id = create_giveaway(title, duration, num_winners, organizer)

        end_time = datetime.now() + timedelta(minutes=duration)
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

        required_channels_text = "\n".join(get_required_channels())

        buttons = [[InlineKeyboardButton("✅ Join & Participate", callback_data=f"join_{giveaway_id}")]]
        keyboard = InlineKeyboardMarkup(buttons)

        message = (
            f"📢 **Grab Your Goodies!**\n\n"
            f"🎁 **Prize:** [Click Here]({title})\n"
            f"⏳ **Ends At:** {end_time_str} WIB\n"
            f"🏆 **Winners:** {num_winners}\n"
            f"👤 **Hosted By:** {organizer}\n\n"
            f"📌 **Join these channels first:**\n{required_channels_text}\n\n"
            "Then, click the button below to join the giveaway!"
        )

        await context.bot.send_message(
            chat_id=get_post_channel(),
            text=message,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

        await update.message.reply_text("Giveaway posted!")

    except ValueError:
        await update.message.reply_text("Duration & winner count must be integers.")

async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        user_id = query.from_user.id
        username = query.from_user.username or f"user_{user_id}"
        data = query.data.split("_")

        if len(data) < 2 or not data[1].isdigit():
            await query.answer("❌ Invalid giveaway!", show_alert=True)
            return

        giveaway_id = int(data[1])
        participants = get_participants(giveaway_id)

        if user_id in participants:
            await query.answer("✅ You already joined!", show_alert=True)
            return

        is_joined = await check_participation(user_id)
        if is_joined:
            add_participant(giveaway_id, user_id, username)
            message = "✅ Successfully joined!"
        else:
            message = "❌ Join all required channels first!"

        await query.answer(message, show_alert=True)

    except Exception as e:
        print(f"Error in join_giveaway: {e}")
        await query.answer("⚠️ Something went wrong!", show_alert=True)

async def check_giveaway_expiry(context: ContextTypes.DEFAULT_TYPE):
    expired = get_expired_giveaways()
    for giveaway in expired:
        participants = get_participants(giveaway["id"])
        total = len(participants)
        end_time = giveaway["end_time"]

        if participants:
            winners = random.sample(participants, min(len(participants), giveaway["num_winners"]))
            winner_mentions = ", ".join([f"@{w}" for w in winners])
            message = (
                f"🎁 **Prize:** [Click Here]({giveaway['title']})\n"
                f"📆 **Ended At:** {end_time} WIB\n"
                f"🏆 **Winners:** {winner_mentions}\n"
                f"👥 **Participants:** {total}\n"
                f"👤 **Hosted By:** {giveaway['organizer']}\n\n"
                f"🎉 Congrats!"
            )
        else:
            message = (
                f"🎁 **Prize:** [Click Here]({giveaway['title']})\n"
                f"📆 **Ended At:** {end_time} WIB\n"
                f"🏆 No participants 😢\n"
                f"👤 **Hosted By:** {giveaway['organizer']}"
            )

        await context.bot.send_message(get_post_channel(), message, parse_mode="Markdown")
        delete_giveaway(giveaway["id"])

async def set_post_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setpostchannel @channel")
        return
    set_post_channel(context.args[0])
    await update.message.reply_text("✅ Post channel updated.")

async def add_required_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addrequired @channel")
        return
    add_required_channel(context.args[0])
    await update.message.reply_text("✅ Required channel added.")

async def remove_required_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removerequired @channel")
        return
    remove_required_channel(context.args[0])
    await update.message.reply_text("✅ Required channel removed.")

async def view_settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_channel = get_post_channel()
    required = get_required_channels()
    await update.message.reply_text(
        f"📦 Settings:\nPost Channel: {post_channel}\nRequired Channels:\n" + "\n".join(required)
    )

# ===================== MAIN =====================
def main():
    if os.path.exists("giveaway.db"):
        os.remove("giveaway.db")
        print("🗑️ Database lama dihapus!")

    app = Application.builder().token(TOKEN).pool_timeout(10).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgiveaway", new_giveaway))
    app.add_handler(CommandHandler("setpostchannel", set_post_channel_cmd))
    app.add_handler(CommandHandler("addrequired", add_required_cmd))
    app.add_handler(CommandHandler("removerequired", remove_required_cmd))
    app.add_handler(CommandHandler("viewsettings", view_settings_cmd))
    app.add_handler(CallbackQueryHandler(join_giveaway, pattern="^join_"))

    app.job_queue.run_repeating(check_giveaway_expiry, interval=60, first=10)

    logging.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
