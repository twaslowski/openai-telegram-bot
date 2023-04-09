import logging
import os

import openai
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext

from src.data.message import Message
from src.data.prompts import SYSTEM_UNABLE_TO_RESPOND
from src.data.session import get_user_session, Session
from src.data.edit_message import EditMessage
from src.text_to_speech import text_to_speech


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = get_user_session(update.effective_user.id)
    original_text = update.message.reply_to_message.text
    session.messages.append(Message(role="assistant", content=original_text))
    session.save()
    await handle_prompt(update, update.message.text)


async def handle_error(update: object, context: CallbackContext) -> None:
    logging.error(f"Update {update} caused error {context.error}")
    await update.message.reply_text("I'm very sorry, an error occured.")
    raise context.error


async def handle_text_message(update: Update, _) -> None:
    logging.info(f"Received message from {update.effective_user.id}: {update.message.text}")
    await handle_prompt(update, update.message.text)


async def handle_prompt(update: Update, prompt, msg: EditMessage = None) -> None:
    if msg is None:
        msg = EditMessage(await update.message.reply_text("Thinking ..."))

    # retrieve user session and append prompt
    session = get_user_session(update.effective_user.id)
    session.add_message(Message(role="user", content=prompt))
    logging.info(f"Effective prompt: {prompt}")

    # get chatgpt response
    openai_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=session.get_messages()
    )

    response = openai_response["choices"][0]["message"]["content"]
    session.add_message(Message(role="assistant", content=response))
    logging.info(f"Response: {response}")
    await send_response(session, response, update, msg)


async def send_response(session: Session, response: str, update: Update, msg: EditMessage):
    if should_perform_tts(response, session):
        try:
            await msg.message.edit_text("Converting response to speech ...")
            tts_file = text_to_speech(response, session.tts.voice)
            await update.message.reply_voice(voice=open(tts_file, "rb"))
            os.remove(tts_file)
        except RuntimeError as e:
            logging.error("Failed to retrieve TTS, reason: " + str(e))
            session.reset_tts()
            await msg.message.edit_text(f"Unfortunately there was an error retrieving the TTS. "
                                        f"Your text response is below. TTS will be disabled for now.\n{response}")
    else:
        await msg.message.edit_text(msg.replace(response))


def should_perform_tts(response, session):
    return session.tts.is_active() and SYSTEM_UNABLE_TO_RESPOND not in response
