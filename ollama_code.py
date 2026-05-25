#!/usr/bin/env python3
"""Neura AI v1.0 - Beautiful TUI for Ollama with PDF Export & Import"""

import asyncio
import json
import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

# PDF export support
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, black
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Preformatted
    )
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# PDF import support
try:
    from pypdf import PdfReader
    PDF_READ_AVAILABLE = True
except ImportError:
    PDF_READ_AVAILABLE = False

OLLAMA_URL = "http://localhost:11434"
CONFIG_DIR = Path.home() / ".config" / "neura-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "error.log"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# Save exports to Documents\history (or OneDrive\Documents\history if synced)
def _get_docs_dir():
    """Find user's Documents folder, preferring OneDrive if synced."""
    home = Path.home()
    candidates = [
        home / "OneDrive" / "Documents",
        home / "Documents",
        home,
    ]
    for p in candidates:
        if p.exists():
            return p
    return home


HISTORY_DIR = _get_docs_dir() / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = {
    "last_model": "",
    "ollama_url": OLLAMA_URL,
    "system_prompt": "You are Neura, a helpful AI assistant.",
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_tokens": -1,
    "repeat_penalty": 1.1,
    "seed": None,
    "keep_alive": "30m",
    "num_ctx": 4096,
    "show_timestamps": True,
}


def log_error(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}] {msg}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


def load_config():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        log_error(f"save_config: {e}")


MASCOT_SMALL = ["┌────┐", "│■  ■│", "│ __ │", "├────┤", "│░░░░│", "└┬──┬┘"]
MASCOT_LARGE = [
    "   ╭──────╮   ", "   │ ■  ■ │   ", "   │  __  │   ",
    "  ╭┴──────┴╮  ", " ╱│ NEURA  │╲ ", "╱ ╰────────╯ ╲", "╲_╱╲_╱╲_╱╲_╱╲╱",
]


class OllamaClient:
    def __init__(self, url):
        self.url = url
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0),
        )

    async def list_models(self):
        try:
            r = await self.client.get(f"{self.url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception as e:
            log_error(f"list_models: {e}")
            return []

    async def ping(self):
        try:
            r = await self.client.get(f"{self.url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    async def chat_stream(self, model, messages, options, keep_alive="30m"):
        payload = {
            "model": model, "messages": messages, "stream": True,
            "keep_alive": keep_alive, "options": options,
        }
        async with self.client.stream(
            "POST", f"{self.url}/api/chat", json=payload,
            timeout=httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"HTTP {resp.status_code}: {body.decode(errors='ignore')[:200]}")
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    yield None
                    return
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content

    async def close(self):
        try:
            await self.client.aclose()
        except Exception:
            pass


COMMANDS = [
    ("/help", "Show all commands"), ("/quit", "Exit"), ("/exit", "Exit"),
    ("/clear", "Clear conversation"), ("/reset", "Reset all settings"),
    ("/models", "Pick from your models"), ("/model <name>", "Switch model"),
    ("/modelinfo", "Show model details"), ("/pull <name>", "Download a model"),
    ("/save", "Save conversation as JSON"),
    ("/export", "Export as PDF to Documents/history"),
    ("/import <path>", "Import a PDF into the conversation"),
    ("/history", "Open history folder in Explorer"),
    ("/system <text>", "Set system prompt"), ("/persona <name>", "Set persona"),
    ("/temperature <v>", "Temperature 0-2"), ("/top_p <v>", "Top-P 0-1"),
    ("/top_k <v>", "Top-K"), ("/max_tokens <v>", "Max tokens"),
    ("/seed <v>", "Random seed"), ("/repeat_penalty <v>", "Repeat penalty"),
    ("/num_ctx <v>", "Context window"), ("/keep_alive <v>", "Keep model loaded"),
    ("/settings", "Show settings"), ("/url <url>", "Set Ollama URL"),
    ("/ping", "Test connection"), ("/reconnect", "Reconnect & rescan"),
    ("/stats", "Session stats"), ("/version", "Version info"),
    ("/copy", "Copy last response"), ("/retry", "Retry last message"),
    ("/edit", "Edit last message"), ("/cancel", "Cancel stream"),
    ("/timestamps", "Toggle timestamps"),
]

PERSONAS = {
    "coder": "You are an expert programmer. Write clean, well-documented code.",
    "teacher": "You are a patient teacher. Explain step-by-step.",
    "writer": "You are a creative writer.",
    "analyst": "You are a data analyst.",
    "devops": "You are a DevOps expert.",
    "security": "You are a cybersecurity expert.",
    "architect": "You are a software architect.",
    "reviewer": "You are a code reviewer.",
    "debug": "You are a debugging expert.",
}


class ModelSelectScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel")]

    def __init__(self, models, current_model, first_launch=False):
        super().__init__()
        self.all_models = list(models) if models else []
        self.filtered = list(self.all_models)
        self.current_model = current_model or ""
        self.first_launch = first_launch

    def compose(self) -> ComposeResult:
        title = "🤖 Select a Model to Begin" if self.first_launch else "Select Model"
        with Container(id="modal-container"):
            yield Label(f"  {title}", id="modal-title")
            yield Label(
                f"  Found [bold green]{len(self.all_models)}[/] models · Esc to cancel",
                id="modal-hint",
            )
            yield Input(placeholder="🔍 Type to filter...", id="model-search")
            yield ListView(id="model-list")

    def on_mount(self):
        try:
            self._refresh("")
            lv = self.query_one("#model-list", ListView)
            for i, m in enumerate(self.filtered):
                if m.get("name") == self.current_model:
                    lv.index = i
                    break
            lv.focus()
        except Exception as e:
            log_error(f"ModelSelect on_mount: {e}")

    def _fmt_size(self, b):
        if not b:
            return "?"
        if b >= 1_000_000_000:
            return f"{b/1e9:.1f}GB"
        if b >= 1_000_000:
            return f"{b/1e6:.0f}MB"
        return f"{b}B"

    def _family(self, m):
        d = m.get("details") or {}
        f = d.get("family", "")
        if f:
            return f
        name = m.get("name", "").lower().split(":")[0]
        for fam in ["qwen", "llama", "mistral", "gpt-oss", "gemma", "phi",
                    "deepseek", "codellama", "codestral", "starcoder",
                    "tinyllama", "vicuna", "wizard", "dolphin", "falcon"]:
            if fam in name:
                return fam
        return name.split("-")[0] if "-" in name else name

    def _params(self, m):
        d = m.get("details") or {}
        ps = d.get("parameter_size", "")
        if ps:
            return ps
        match = re.search(r"(\d+\.?\d*)\s*[bm]\b", m.get("name", "").lower())
        return f"{match.group(1)}B" if match else ""

    def _quant(self, m):
        d = m.get("details") or {}
        return d.get("quantization_level", "")

    def _refresh(self, query):
        try:
            q = query.lower().strip()
            if q:
                self.filtered = [
                    m for m in self.all_models
                    if q in m.get("name", "").lower()
                    or q in self._family(m).lower()
                    or q in self._params(m).lower()
                ]
            else:
                self.filtered = list(self.all_models)
            self.filtered.sort(key=lambda m: (m.get("name") != self.current_model, m.get("size", 0)))

            lv = self.query_one("#model-list", ListView)
            lv.clear()

            if not self.all_models:
                lv.append(ListItem(Label("  [red]No models installed![/]")))
                lv.append(ListItem(Label("  [#75718e]Run: ollama pull llama3.2[/]")))
                return

            if not self.filtered:
                lv.append(ListItem(Label(f"  [yellow]No matches for '{query}'[/]")))
                return

            for m in self.filtered:
                name = m.get("name", "?")
                size = self._fmt_size(m.get("size", 0))
                fam = self._family(m)
                par = self._params(m)
                qnt = self._quant(m)
                is_cur = name == self.current_model
                mark = "[bold green]●[/]" if is_cur else " "
                tags = []
                if fam: tags.append(f"[#8be9fd]{fam}[/]")
                if par: tags.append(f"[#bd93f9]{par}[/]")
                if qnt: tags.append(f"[#75718e]{qnt}[/]")
                tags.append(f"[#f1fa8c]{size}[/]")
                lv.append(ListItem(Label(f" {mark} [bold white]{name}[/]   {' · '.join(tags)}")))
        except Exception as e:
            log_error(f"_refresh: {e}")

    def on_input_changed(self, event):
        if event.input.id == "model-search":
            self._refresh(event.value)

    def on_input_submitted(self, event):
        if event.input.id == "model-search":
            try:
                self.query_one("#model-list", ListView).focus()
            except Exception:
                pass

    def action_cancel(self):
        self.dismiss("")

    def on_list_view_selected(self, event):
        try:
            lv = self.query_one("#model-list", ListView)
            idx = lv.index if lv.index is not None else 0
            if 0 <= idx < len(self.filtered):
                self.dismiss(self.filtered[idx].get("name", ""))
            else:
                self.dismiss("")
        except Exception as e:
            log_error(f"on_list_view_selected: {e}")
            self.dismiss("")


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,q", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("  Neura AI v1.0 — Help", id="modal-title")
            with VerticalScroll(id="help-scroll"):
                lines = []
                for m in MASCOT_SMALL:
                    lines.append(f"  [orange1]{m}[/]")
                lines.append("\n  [bold cyan]─── Keyboard ───[/]")
                for k, d in [("Enter", "Send message"), ("Ctrl+C", "Cancel/quit"),
                             ("Ctrl+Q", "Quit"), ("?", "Help")]:
                    lines.append(f"  [cyan]{k:14}[/]  {d}")
                lines.append("\n  [bold cyan]─── Commands ───[/]")
                for cmd, desc in COMMANDS:
                    lines.append(f"  [green]{cmd:22}[/]  {desc}")
                lines.append("\n  [bold cyan]─── Personas (/persona <name>) ───[/]")
                for name in PERSONAS:
                    lines.append(f"  [magenta]{name}[/]")
                yield Static("\n".join(lines))
            yield Label("  Press Esc to close", id="modal-hint")

    def action_close(self):
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("y,Y", "yes"), Binding("n,N,escape", "no")]

    def __init__(self, title, message):
        super().__init__()
        self.title_text = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container"):
            yield Label(f"  {self.title_text}", id="modal-title")
            yield Label(f"  {self.message}")
            yield Label("  [green][y][/] Yes    [red][n/Esc][/] No", id="modal-hint")

    def action_yes(self):
        self.dismiss(True)

    def action_no(self):
        self.dismiss(False)


class NeuraAIApp(App):
    CSS = """
    Screen { background: #19192a; color: #dcdceb; }
    #header-container { height: 8; background: #19192a; padding: 0 1; }
    #mascot { width: 10; color: #e67e58; }
    #info-panel { width: 1fr; }
    #app-name { color: #f1fa8c; text-style: bold; }
    #app-version { color: #75718e; }
    #app-model { color: #8be9fd; text-style: bold; }
    #app-cwd { color: #75718e; }
    #app-status { color: #50fa7b; }
    #chat-scroll {
        height: 1fr; background: #19192a;
        border-top: solid #37374b; border-bottom: solid #37374b;
        padding: 0 1;
    }
    #input-container { height: 5; background: #1e1e2a; padding: 0 1; }
    #user-input {
        background: #1e1e2a; border: none; color: #ffffff;
        height: 3; padding: 1 0;
    }
    #user-input:focus { border: none; }
    #footer-bar { height: 1; color: #75718e; background: #19192a; padding: 0 1; }
    ModalScreen { align: center middle; }
    #modal-container {
        width: 90; max-width: 95%; height: auto; max-height: 90%;
        background: #23233a; border: round #8be9fd; padding: 1 2;
    }
    #confirm-container {
        width: 50; height: auto; background: #23233a;
        border: round #8be9fd; padding: 1 2;
    }
    #modal-title { color: #f1fa8c; text-style: bold; padding-bottom: 1; }
    #modal-hint { color: #75718e; padding-top: 1; }
    #model-list { height: 18; background: #23233a; border: none; }
    #model-search { background: #2a2a40; border: solid #8be9fd; margin-bottom: 1; }
    #help-scroll { height: 25; background: #23233a; }
    ListItem { background: #23233a; color: #dcdceb; padding: 0 1; }
    ListItem:hover { background: #32324a; }
    ListItem.--highlight { background: #44475a; color: #8be9fd; text-style: bold; }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_quit", priority=True),
        Binding("ctrl+q", "quit_app"),
    ]

    is_streaming = reactive(False)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.client = OllamaClient(self.config["ollama_url"])
        self.messages = []
        self.chat_log = []
        self.session_start = time.time()
        self.total_tokens = 0
        self.total_messages = 0
        self.available_models = []
        self.cancel_requested = False
        self.current_model = self.config.get("last_model", "")
        self.status_message = ""
        self.status_color = "green"
        self.connection_status = "checking"
        self._current_stream_text = ""
        self._stream_tokens = 0
        self._stream_start = 0
        self._modal_open = False

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="header-container"):
                yield Static("\n".join(MASCOT_SMALL), id="mascot")
                with Vertical(id="info-panel"):
                    yield Static(" neura-ai", id="app-name")
                    yield Static("    Neura AI v1.0", id="app-version")
                    yield Static(f"    {self.current_model or '(no model)'} · Local Ollama", id="app-model")
                    yield Static(f"    {os.getcwd()}", id="app-cwd")
                    yield Static("    [yellow]○[/] Connecting...", id="app-status")
            with VerticalScroll(id="chat-scroll"):
                yield Static("", id="chat-content")
            with Container(id="input-container"):
                yield Input(placeholder="❯  Type a message or /help...", id="user-input")
            yield Static("  ? help  │  /models  │  /import  │  /export  │  Ctrl+Q quit", id="footer-bar")

    async def on_mount(self):
        self.title = "Neura AI"
        self.set_interval(0.1, self._tick)
        await self._connect_and_setup()

    async def _connect_and_setup(self):
        try:
            connected = await self.client.ping()
            if not connected:
                self.connection_status = "disconnected"
                self._set_status("Cannot connect. Run: ollama serve", "red")
                self._update_header_safe()
                self._refresh_chat_safe()
                return

            self.connection_status = "connected"
            self.available_models = await self.client.list_models()
            model_names = [m.get("name") for m in self.available_models]

            self._set_status(f"Ready · {len(self.available_models)} models", "green")
            self._update_header_safe()
            self._refresh_chat_safe()

            need_picker = not self.current_model or self.current_model not in model_names
            if need_picker and self.available_models:
                self._open_model_picker(first_launch=True)
        except Exception as e:
            log_error(f"_connect_and_setup: {e}")

    def _open_model_picker(self, first_launch=False):
        if self._modal_open:
            return
        self._modal_open = True

        def on_chosen(selected):
            self._modal_open = False
            try:
                if selected and selected != self.current_model:
                    self.current_model = selected
                    self.config["last_model"] = selected
                    save_config(self.config)
                    self._set_status(f"Ready · {selected}", "green")
                    self._update_header_safe()
                    self._refresh_chat_safe()
                elif first_launch and not self.current_model and self.available_models:
                    first = self.available_models[0].get("name", "")
                    if first:
                        self.current_model = first
                        self.config["last_model"] = first
                        save_config(self.config)
                        self._set_status(f"Ready · {first}", "green")
                        self._update_header_safe()
                        self._refresh_chat_safe()
            except Exception as e:
                log_error(f"on_model_chosen: {e}")

        try:
            screen = ModelSelectScreen(self.available_models, self.current_model, first_launch=first_launch)
            self.push_screen(screen, on_chosen)
        except Exception as e:
            log_error(f"_open_model_picker: {e}")
            self._modal_open = False

    def _set_status(self, msg, color="green"):
        self.status_message = msg
        self.status_color = color

    def _update_header_safe(self):
        try:
            self.query_one("#app-model", Static).update(
                f"    [#8be9fd][b]{self.current_model or '(no model)'}[/b][/] · Local Ollama"
            )
            icons = {
                "connected": "[green]●[/] Connected",
                "disconnected": "[red]●[/] Disconnected",
                "checking": "[yellow]○[/] Checking...",
            }
            now = datetime.now().strftime("%H:%M")
            status = f"[{self.status_color}]{self.status_message}[/]" if self.status_message else "[green]Ready[/]"
            self.query_one("#app-status", Static).update(
                f"    {status}  {icons.get(self.connection_status, '')}  [#75718e]{now}[/]"
            )
        except Exception as e:
            log_error(f"_update_header_safe: {e}")

    def _refresh_chat_safe(self):
        try:
            content = self.query_one("#chat-content", Static)
        except Exception:
            return
        try:
            if not self.chat_log and not self.is_streaming:
                lines = [""]
                for m in MASCOT_LARGE:
                    lines.append(f"  [orange1]{m}[/]")
                lines.append("")
                lines.append("  [bold yellow]Welcome to Neura AI![/]")
                if self.current_model:
                    lines.append(f"  [cyan]Model:[/] [bold]{self.current_model}[/]")
                else:
                    lines.append("  [yellow]No model. Type /models to pick one.[/]")
                lines.append("")
                if self.connection_status == "disconnected":
                    lines.append("  [red]✗ Ollama not running![/]")
                    lines.append("  [#75718e]Start with: ollama serve[/]")
                    lines.append("  [#75718e]Then type: /reconnect[/]")
                else:
                    lines.append(f"  [#75718e]Found {len(self.available_models)} models. Type /models to switch.[/]")
                    lines.append("  [#75718e]Type ? or /help for commands.[/]")
                    lines.append(f"  [#75718e]History folder: {HISTORY_DIR}[/]")
                content.update("\n".join(lines))
                return

            lines = []
            for entry in self.chat_log:
                role = entry["role"]
                text = entry["content"]
                ts = entry.get("timestamp", "")
                dur = entry.get("duration")
                tokens = entry.get("tokens")
                lines.append("")
                if role == "user":
                    ts_s = f"[#75718e]\\[{ts}][/] " if ts and self.config.get("show_timestamps") else ""
                    lines.append(f"[bold #8be9fd]❯[/] {ts_s}[bold white]{self._esc(text)}[/]")
                elif role == "assistant":
                    ts_s = f"[#75718e]\\[{ts}][/] " if ts and self.config.get("show_timestamps") else ""
                    lines.append(f"[#75718e]└[/] {ts_s}")
                    for ln in text.split("\n"):
                        lines.append(f"  [#dcdceb]{self._esc(ln)}[/]")
                    if dur:
                        info = f"  [yellow]✦[/] [#75718e]Brewed for {self._fmt_dur(dur)}[/]"
                        if tokens:
                            info += f" [#75718e]· ~{tokens} tokens · {tokens/dur:.1f} tok/s[/]"
                        lines.append(info)
                elif role == "system":
                    lines.append("[cyan]ℹ System[/]")
                    for ln in text.split("\n"):
                        lines.append(f"  [#75718e]{self._esc(ln)}[/]")
                elif role == "error":
                    lines.append(f"[red]✗ {self._esc(text)}[/]")

            if self.is_streaming:
                lines.append("\n[#75718e]└[/]")
                if self._current_stream_text:
                    for ln in self._current_stream_text.split("\n"):
                        lines.append(f"  [#dcdceb]{self._esc(ln)}[/]")
                elapsed = time.time() - self._stream_start
                sp = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
                spinner = sp[int(elapsed*12) % len(sp)]
                tps = self._stream_tokens/elapsed if elapsed > 0 else 0
                if self._stream_tokens == 0 and elapsed > 2:
                    lines.append(f"  [bold yellow]{spinner}[/] [#75718e]Loading model into memory... ({self._fmt_dur(elapsed)})[/]")
                else:
                    lines.append(f"  [bold cyan]{spinner}[/] [#75718e]{self._fmt_dur(elapsed)} · {self._stream_tokens} tokens · {tps:.1f} tok/s[/]")

            content.update("\n".join(lines))
            try:
                self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=False)
            except Exception:
                pass
        except Exception as e:
            log_error(f"_refresh_chat_safe: {e}")

    def _esc(self, t):
        return t.replace("[", "\\[")

    def _fmt_dur(self, s):
        if s >= 60: return f"{int(s//60)}m {int(s%60)}s"
        if s >= 1: return f"{s:.2f}s"
        return f"{int(s*1000)}ms"

    def _tick(self):
        try:
            if self.is_streaming:
                self._refresh_chat_safe()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted):
        try:
            if event.input.id != "user-input":
                return
            text = event.value.strip()
            event.input.value = ""
            if not text or self.is_streaming:
                return
            if text.startswith("/") or text == "?":
                await self._handle_command(text)
            else:
                await self._send_message(text)
        except Exception as e:
            log_error(f"on_input_submitted: {e}")

    async def _send_message(self, content):
        try:
            if self.connection_status != "connected":
                self._set_status("Not connected!", "red")
                self._update_header_safe()
                return
            if not self.current_model:
                self._set_status("Pick a model first!", "red")
                self._update_header_safe()
                self._open_model_picker(first_launch=False)
                return

            self.messages.append({"role": "user", "content": content})
            self.chat_log.append({
                "role": "user", "content": content,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
            self.total_messages += 1
            self._refresh_chat_safe()

            self.cancel_requested = False
            self._current_stream_text = ""
            self._stream_tokens = 0
            self._stream_start = time.time()
            self.is_streaming = True
            self.run_worker(self._stream_response(), exclusive=True, name="stream")
        except Exception as e:
            log_error(f"_send_message: {e}")

    async def _stream_response(self):
        try:
            msgs = []
            if self.config.get("system_prompt"):
                msgs.append({"role": "system", "content": self.config["system_prompt"]})
            msgs.extend(self.messages)
            opts = {
                "temperature": self.config["temperature"],
                "top_p": self.config["top_p"],
                "top_k": self.config["top_k"],
                "num_predict": self.config["max_tokens"],
                "repeat_penalty": self.config["repeat_penalty"],
                "num_ctx": self.config.get("num_ctx", 4096),
            }
            if self.config.get("seed") is not None:
                opts["seed"] = self.config["seed"]

            last = 0
            async for chunk in self.client.chat_stream(
                self.current_model, msgs, opts,
                keep_alive=self.config.get("keep_alive", "30m"),
            ):
                if self.cancel_requested:
                    self._current_stream_text += "\n[Cancelled]"
                    break
                if chunk is None:
                    break
                self._current_stream_text += chunk
                self._stream_tokens += 1
                now = time.time()
                if now - last > 0.05:
                    self._refresh_chat_safe()
                    last = now

            dur = time.time() - self._stream_start
            self.chat_log.append({
                "role": "assistant",
                "content": self._current_stream_text or "(empty response)",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "duration": dur, "tokens": self._stream_tokens,
            })
            self.messages.append({"role": "assistant", "content": self._current_stream_text})
            self.total_tokens += self._stream_tokens
            self.is_streaming = False
            self._refresh_chat_safe()
        except Exception as e:
            log_error(f"_stream_response: {e}")
            self.chat_log.append({
                "role": "error", "content": f"API Error: {e}",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
            self.is_streaming = False
            try:
                self._refresh_chat_safe()
            except Exception:
                pass

    def _export_pdf(self):
        """Export conversation as a styled PDF to Documents/history/"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_model = (self.current_model or "nomodel").replace(":", "_").replace("/", "_")
        path = HISTORY_DIR / f"neura_{ts}_{safe_model}.pdf"

        doc = SimpleDocTemplate(
            str(path),
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title=f"Neura AI Chat - {self.current_model}",
            author="Neura AI",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title", parent=styles["Heading1"], fontSize=20,
            textColor=HexColor("#1a1a2e"), spaceAfter=8, alignment=TA_LEFT,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle", parent=styles["Normal"], fontSize=10,
            textColor=HexColor("#75718e"), spaceAfter=20,
        )
        user_label = ParagraphStyle(
            "UserLabel", parent=styles["Heading3"], fontSize=11,
            textColor=HexColor("#0066cc"), spaceBefore=12, spaceAfter=4,
        )
        assistant_label = ParagraphStyle(
            "AssistantLabel", parent=styles["Heading3"], fontSize=11,
            textColor=HexColor("#cc6600"), spaceBefore=12, spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"], fontSize=10,
            textColor=black, spaceAfter=6, leading=14,
        )
        code_style = ParagraphStyle(
            "Code", parent=styles["Code"], fontSize=9,
            textColor=HexColor("#1a1a2e"), backColor=HexColor("#f0f0f5"),
            borderColor=HexColor("#cccccc"), borderWidth=0.5, borderPadding=8,
            leftIndent=10, rightIndent=10, spaceAfter=8,
            fontName="Courier", leading=11,
        )
        meta_style = ParagraphStyle(
            "Meta", parent=styles["Normal"], fontSize=8,
            textColor=HexColor("#999999"), spaceAfter=4,
        )

        story = []
        story.append(Paragraph("Neura AI Conversation", title_style))
        msg_count = len([e for e in self.chat_log if e["role"] in ("user", "assistant")])
        story.append(Paragraph(
            f"<b>Model:</b> {self._html_escape(self.current_model)}<br/>"
            f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}<br/>"
            f"<b>Messages:</b> {msg_count}",
            subtitle_style,
        ))
        story.append(Spacer(1, 0.1 * inch))

        for entry in self.chat_log:
            role = entry["role"]
            content = entry["content"]
            ts_str = entry.get("timestamp", "")

            if role == "user":
                story.append(Paragraph(
                    f"❯ User <font size='8' color='#999999'>[{ts_str}]</font>",
                    user_label,
                ))
                story.extend(self._render_pdf_content(content, body_style, code_style))

            elif role == "assistant":
                story.append(Paragraph(
                    f"⬡ Neura <font size='8' color='#999999'>[{ts_str}]</font>",
                    assistant_label,
                ))
                story.extend(self._render_pdf_content(content, body_style, code_style))

                dur = entry.get("duration")
                tokens = entry.get("tokens")
                if dur:
                    info = f"Generated in {self._fmt_dur(dur)}"
                    if tokens:
                        info += f" · ~{tokens} tokens · {tokens/dur:.1f} tok/s"
                    story.append(Paragraph(info, meta_style))

            elif role == "system":
                story.append(Paragraph("ℹ <i>System</i>", meta_style))
                story.append(Paragraph(self._html_escape(content), body_style))

        doc.build(story)
        return path

    def _render_pdf_content(self, content, body_style, code_style):
        """Split content into text + code block paragraphs."""
        elements = []
        parts = content.split("```")
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            if i % 2 == 0:
                escaped = self._html_escape(part).replace("\n", "<br/>")
                if escaped.strip():
                    elements.append(Paragraph(escaped, body_style))
            else:
                lines = part.split("\n", 1)
                code = lines[1] if len(lines) > 1 and ' ' not in lines[0].strip() else part
                code = code.rstrip()
                if code:
                    elements.append(Preformatted(code, code_style))
        return elements

    def _html_escape(self, text):
        """Escape HTML/XML special chars for reportlab."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    def _import_pdf(self, raw_path):
        """Read a PDF and inject its content into the conversation."""
        path_str = raw_path.strip().strip('"').strip("'")
        path_str = os.path.expandvars(os.path.expanduser(path_str))
        path = Path(path_str)

        if not path.exists():
            search_dirs = [
                Path.cwd(),
                HISTORY_DIR,
                Path.home() / "Desktop",
                Path.home() / "Downloads",
                Path.home() / "Documents",
                Path.home() / "OneDrive" / "Documents",
                Path.home() / "OneDrive" / "Desktop",
            ]
            for d in search_dirs:
                candidate = d / path.name
                if candidate.exists():
                    path = candidate
                    break

        if not path.exists():
            self._set_status(f"File not found: {raw_path}", "red")
            return

        if path.suffix.lower() != ".pdf":
            self._set_status(f"Not a PDF: {path.name}", "red")
            return

        try:
            reader = PdfReader(str(path))
            num_pages = len(reader.pages)

            text_parts = []
            for i, page in enumerate(reader.pages, 1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"--- Page {i} ---\n{page_text.strip()}")

            if not text_parts:
                self._set_status(f"PDF has no extractable text (image-only?)", "yellow")
                return

            full_text = "\n\n".join(text_parts)
            char_count = len(full_text)
            word_count = len(full_text.split())

            injection = (
                f"[Imported PDF: {path.name}]\n"
                f"[Pages: {num_pages} · Words: ~{word_count} · Chars: {char_count}]\n\n"
                f"{full_text}"
            )

            self.messages.append({"role": "user", "content": injection})

            self.chat_log.append({
                "role": "user",
                "content": f"📄 Imported PDF: {path.name} ({num_pages} pages, ~{word_count} words)",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })

            preview = full_text[:500] + ("..." if len(full_text) > 500 else "")
            self.chat_log.append({
                "role": "system",
                "content": (
                    f"PDF loaded into context!\n"
                    f"  File: {path}\n"
                    f"  Pages: {num_pages}\n"
                    f"  Words: ~{word_count}\n"
                    f"  Characters: {char_count}\n\n"
                    f"Preview (first 500 chars):\n{preview}\n\n"
                    f"You can now ask questions about this PDF!"
                ),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })

            self.total_messages += 1
            self._refresh_chat_safe()
            self._set_status(f"Imported {path.name} ({num_pages} pages)", "green")
        except Exception as e:
            log_error(f"_import_pdf: {e}")
            self._set_status(f"Import failed: {e}", "red")

    async def _handle_command(self, text):
        try:
            if text == "?":
                self._open_help()
                return
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/help", "/?"):
                self._open_help()
            elif cmd in ("/quit", "/exit"):
                self._open_confirm("Quit?", "Are you sure?", lambda ok: self.exit() if ok else None)
            elif cmd == "/clear":
                def on_clear(ok):
                    if ok:
                        self.messages.clear()
                        self.chat_log.clear()
                        self._refresh_chat_safe()
                self._open_confirm("Clear?", "Clear conversation?", on_clear)
            elif cmd == "/reset":
                self.messages.clear()
                self.chat_log.clear()
                saved = self.current_model
                self.config = DEFAULT_CONFIG.copy()
                self.config["last_model"] = saved
                save_config(self.config)
                self._refresh_chat_safe()
                self._set_status("Reset!", "yellow")
                self._update_header_safe()
            elif cmd == "/models":
                if self.connection_status != "connected":
                    if await self.client.ping():
                        self.connection_status = "connected"
                if self.connection_status == "connected":
                    self.available_models = await self.client.list_models()
                self._open_model_picker(first_launch=False)
            elif cmd == "/model":
                if arg:
                    self.current_model = arg
                    self.config["last_model"] = arg
                    save_config(self.config)
                    self._set_status(f"Switched to {arg}", "green")
                else:
                    self._set_status(f"Current: {self.current_model}", "cyan")
                self._update_header_safe()
            elif cmd == "/modelinfo":
                info = (f"Model: {self.current_model}\n"
                        f"URL: {self.config['ollama_url']}\n"
                        f"Temperature: {self.config['temperature']}\n"
                        f"Context: {self.config.get('num_ctx', 4096)}\n"
                        f"Keep Alive: {self.config.get('keep_alive', '30m')}")
                self.chat_log.append({"role": "system", "content": info,
                                      "timestamp": datetime.now().strftime("%H:%M:%S")})
                self._refresh_chat_safe()
            elif cmd == "/pull":
                if not arg:
                    self._set_status("Usage: /pull <model>", "yellow")
                else:
                    self._set_status(f"Pulling {arg}...", "cyan")
                    self.run_worker(self._pull(arg), exclusive=False)
                self._update_header_safe()
            elif cmd == "/save":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe = (self.current_model or "nomodel").replace(":", "_").replace("/", "_")
                path = HISTORY_DIR / f"neura_{ts}_{safe}.json"
                path.write_text(json.dumps(self.messages, indent=2))
                self._set_status(f"Saved {path.name}", "green")
                self._update_header_safe()
            elif cmd == "/export":
                if not PDF_AVAILABLE:
                    self._set_status("Install: pip install reportlab", "red")
                    self._update_header_safe()
                    return
                if not self.chat_log:
                    self._set_status("Nothing to export yet!", "yellow")
                    self._update_header_safe()
                    return
                try:
                    path = self._export_pdf()
                    self._set_status(f"PDF saved: {path.name}", "green")
                except Exception as e:
                    log_error(f"PDF export: {e}")
                    self._set_status(f"Export failed: {e}", "red")
                self._update_header_safe()
            elif cmd == "/import":
                if not PDF_READ_AVAILABLE:
                    self._set_status("Install: pip install pypdf", "red")
                    self._update_header_safe()
                    return
                if not arg:
                    self._set_status("Usage: /import <path_to_pdf>", "yellow")
                    self._update_header_safe()
                    return
                self._import_pdf(arg)
                self._update_header_safe()
            elif cmd == "/history":
                try:
                    os.startfile(str(HISTORY_DIR))
                    self._set_status(f"Opened {HISTORY_DIR}", "green")
                except Exception as e:
                    self._set_status(f"Could not open: {e}", "red")
                self._update_header_safe()
            elif cmd == "/system":
                if arg:
                    self.config["system_prompt"] = arg
                    save_config(self.config)
                    self._set_status("System prompt set", "green")
                self._update_header_safe()
            elif cmd == "/persona":
                if arg.lower() in PERSONAS:
                    self.config["system_prompt"] = PERSONAS[arg.lower()]
                    save_config(self.config)
                    self._set_status(f"Persona: {arg}", "green")
                else:
                    self._set_status(f"Available: {', '.join(PERSONAS.keys())}", "yellow")
                self._update_header_safe()
            elif cmd in ("/temperature", "/temp"):
                try:
                    self.config["temperature"] = float(arg)
                    save_config(self.config)
                    self._set_status(f"temp={arg}", "green")
                except ValueError:
                    self._set_status(f"Current: {self.config['temperature']}", "cyan")
                self._update_header_safe()
            elif cmd == "/top_p":
                try:
                    self.config["top_p"] = float(arg)
                    save_config(self.config)
                    self._set_status(f"top_p={arg}", "green")
                except ValueError: pass
                self._update_header_safe()
            elif cmd == "/top_k":
                try:
                    self.config["top_k"] = int(arg)
                    save_config(self.config)
                    self._set_status(f"top_k={arg}", "green")
                except ValueError: pass
                self._update_header_safe()
            elif cmd in ("/max_tokens", "/maxtokens"):
                try:
                    self.config["max_tokens"] = int(arg)
                    save_config(self.config)
                    self._set_status(f"max_tokens={arg}", "green")
                except ValueError: pass
                self._update_header_safe()
            elif cmd == "/seed":
                if arg in ("none", "random", ""):
                    self.config["seed"] = None
                else:
                    try: self.config["seed"] = int(arg)
                    except ValueError: pass
                save_config(self.config)
                self._set_status(f"seed={self.config['seed']}", "green")
                self._update_header_safe()
            elif cmd == "/repeat_penalty":
                try:
                    self.config["repeat_penalty"] = float(arg)
                    save_config(self.config)
                    self._set_status(f"repeat_penalty={arg}", "green")
                except ValueError: pass
                self._update_header_safe()
            elif cmd == "/num_ctx":
                try:
                    self.config["num_ctx"] = int(arg)
                    save_config(self.config)
                    self._set_status(f"num_ctx={arg}", "green")
                except ValueError: pass
                self._update_header_safe()
            elif cmd == "/keep_alive":
                if arg:
                    self.config["keep_alive"] = arg
                    save_config(self.config)
                    self._set_status(f"keep_alive={arg}", "green")
                self._update_header_safe()
            elif cmd == "/settings":
                info = "\n".join([f"{k}: {v}" for k, v in self.config.items()])
                info += f"\nHistory folder: {HISTORY_DIR}"
                self.chat_log.append({"role": "system", "content": info,
                                      "timestamp": datetime.now().strftime("%H:%M:%S")})
                self._refresh_chat_safe()
            elif cmd == "/url":
                if arg:
                    self.config["ollama_url"] = arg
                    save_config(self.config)
                    await self.client.close()
                    self.client = OllamaClient(arg)
                    await self._connect_and_setup()
                self._update_header_safe()
            elif cmd == "/ping":
                ok = await self.client.ping()
                self.connection_status = "connected" if ok else "disconnected"
                self._set_status("✓ Connected" if ok else "✗ Failed", "green" if ok else "red")
                self._update_header_safe()
            elif cmd == "/reconnect":
                await self.client.close()
                self.client = OllamaClient(self.config["ollama_url"])
                await self._connect_and_setup()
            elif cmd == "/stats":
                d = time.time() - self.session_start
                info = (f"Duration: {self._fmt_dur(d)}\n"
                        f"Messages: {self.total_messages}\n"
                        f"Tokens: {self.total_tokens}\n"
                        f"Model: {self.current_model}\n"
                        f"History folder: {HISTORY_DIR}")
                self.chat_log.append({"role": "system", "content": info,
                                      "timestamp": datetime.now().strftime("%H:%M:%S")})
                self._refresh_chat_safe()
            elif cmd == "/version":
                pdf_export = "✓ PDF export" if PDF_AVAILABLE else "✗ PDF export (pip install reportlab)"
                pdf_import = "✓ PDF import" if PDF_READ_AVAILABLE else "✗ PDF import (pip install pypdf)"
                self.chat_log.append({"role": "system",
                                      "content": f"Neura AI v1.0\n{pdf_export}\n{pdf_import}",
                                      "timestamp": datetime.now().strftime("%H:%M:%S")})
                self._refresh_chat_safe()
            elif cmd == "/copy":
                last = next((e for e in reversed(self.chat_log) if e["role"] == "assistant"), None)
                if last:
                    try:
                        import pyperclip
                        pyperclip.copy(last["content"])
                        self._set_status("Copied!", "green")
                    except ImportError:
                        self._set_status("pip install pyperclip", "yellow")
                self._update_header_safe()
            elif cmd == "/retry":
                if self.messages and self.messages[-1]["role"] == "assistant":
                    self.messages.pop()
                if self.chat_log and self.chat_log[-1]["role"] == "assistant":
                    self.chat_log.pop()
                self._current_stream_text = ""
                self._stream_tokens = 0
                self._stream_start = time.time()
                self.is_streaming = True
                self.cancel_requested = False
                self.run_worker(self._stream_response(), exclusive=True)
            elif cmd == "/edit":
                last_user = next((m for m in reversed(self.messages) if m["role"] == "user"), None)
                if last_user:
                    if self.messages and self.messages[-1]["role"] == "assistant":
                        self.messages.pop()
                    if self.messages and self.messages[-1]["role"] == "user":
                        self.messages.pop()
                    if self.chat_log and self.chat_log[-1]["role"] == "assistant":
                        self.chat_log.pop()
                    if self.chat_log and self.chat_log[-1]["role"] == "user":
                        self.chat_log.pop()
                    self.query_one("#user-input", Input).value = last_user["content"]
                    self._refresh_chat_safe()
            elif cmd == "/cancel":
                self.cancel_requested = True
            elif cmd == "/timestamps":
                self.config["show_timestamps"] = not self.config.get("show_timestamps", True)
                save_config(self.config)
                self._refresh_chat_safe()
            else:
                self._set_status(f"Unknown: {cmd}", "red")
                self._update_header_safe()
        except Exception as e:
            log_error(f"_handle_command '{text}': {e}")
            self._set_status("Command error (logged)", "red")
            self._update_header_safe()

    def _open_help(self):
        if self._modal_open:
            return
        self._modal_open = True
        def on_close(_):
            self._modal_open = False
        try:
            self.push_screen(HelpScreen(), on_close)
        except Exception as e:
            log_error(f"_open_help: {e}")
            self._modal_open = False

    def _open_confirm(self, title, message, callback):
        if self._modal_open:
            return
        self._modal_open = True
        def on_close(result):
            self._modal_open = False
            try:
                if callback: callback(result)
            except Exception as e:
                log_error(f"confirm callback: {e}")
        try:
            self.push_screen(ConfirmScreen(title, message), on_close)
        except Exception as e:
            log_error(f"_open_confirm: {e}")
            self._modal_open = False

    async def _pull(self, name):
        try:
            r = await self.client.client.post(
                f"{self.config['ollama_url']}/api/pull",
                json={"name": name, "stream": False}, timeout=600,
            )
            if r.status_code == 200:
                self._set_status(f"Pulled {name}!", "green")
                self.available_models = await self.client.list_models()
            else:
                self._set_status("Pull failed", "red")
        except Exception as e:
            log_error(f"_pull: {e}")
            self._set_status("Pull error", "red")
        self._update_header_safe()

    def action_cancel_or_quit(self):
        try:
            if self.is_streaming:
                self.cancel_requested = True
            else:
                self.exit()
        except Exception:
            self.exit()

    def action_quit_app(self):
        self.exit()


def main():
    app = NeuraAIApp()
    try:
        app.run()
    except Exception as e:
        log_error(f"main crash: {e}")
        print(f"\nApp crashed. Check log: {LOG_FILE}")
    finally:
        try:
            asyncio.run(app.client.close())
        except Exception:
            pass


if __name__ == "__main__":
    main()