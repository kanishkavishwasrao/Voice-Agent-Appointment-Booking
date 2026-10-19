"""Voice appointment booking demo.  Run:  python app.py
Mic -> Sarvam STT -> resolver + dialog -> Sarvam TTS.  Typing also works (no API key needed
for the text path, handy for debugging the dialog)."""
import json
import os
import shutil
import time as _time
from datetime import datetime

import gradio as gr

import booking
from resolver import resolve

LOG_DIR = "logs"
os.makedirs(os.path.join(LOG_DIR, "audio"), exist_ok=True)
GREETING = "नमस्ते! आप किस दिन और किस समय आना चाहेंगे?"


def log_turn(audio_path, transcript, reply):
    """Every turn is saved: this is the dataset for your end-to-end eval."""
    saved = None
    if audio_path:
        saved = os.path.join(LOG_DIR, "audio", f"{int(_time.time() * 1000)}.wav")
        shutil.copy(audio_path, saved)
    r = resolve(transcript)
    with open(os.path.join(LOG_DIR, "turns.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"), "audio": saved,
            "transcript": transcript, "parsed": r.describe(), "reply": reply,
        }, ensure_ascii=False) + "\n")


def respond(audio_path, typed, history, sess):
    print("audio_path:", audio_path, "| typed:", repr(typed))
    try:
        if typed and typed.strip():
            text = typed.strip()
        elif audio_path:
            from sarvam_io import stt
            text = stt(audio_path)
            print("transcript:", text)
        else:
            gr.Warning("No audio received. Record first (timer should be above 0:00) or type in the Text box.")
            return history, None, booking.all_bookings(), sess, ""
        reply = booking.handle(sess, text)
        log_turn(audio_path, text, reply)
        history = history + [{"role": "user", "content": text},
                             {"role": "assistant", "content": reply}]
        try:
            from sarvam_io import tts
            speech = tts(reply)
        except Exception as e:
            gr.Warning(f"TTS unavailable: {e}")
            speech = None
        return history, speech, booking.all_bookings(), sess, ""
    except Exception as e:
        print("ERROR:", repr(e))
        gr.Warning(str(e))
        return history, None, booking.all_bookings(), sess, ""

with gr.Blocks(title="Voice Appointment Booking") as demo:
    gr.Markdown("## 🎙️ Voice appointment booking (Hindi / Hinglish)\n"
                'Try: *"kal shaam ko paanch baje ke baad"*, *"parson sawa chaar baje"*, *"aadhe ghante mein"*')
    sess = gr.State(booking.Session())
    chat = gr.Chatbot(value=[{"role": "assistant", "content": GREETING}], height=320)
    with gr.Row():
        mic = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Speak")
        out = gr.Audio(label="Agent", autoplay=True)
    typed = gr.Textbox(placeholder="…or type here (also useful for testing)", label="Text")
    cal = gr.Dataframe(headers=["Date", "Time"], value=booking.all_bookings(), label="Booked slots")

    ins = [mic, typed, chat, sess]
    outs = [chat, out, cal, sess, typed]
    send = gr.Button("Send recording")
    send.click(respond, ins, outs)
    typed.submit(respond, ins, outs)


if __name__ == "__main__":
    demo.launch()