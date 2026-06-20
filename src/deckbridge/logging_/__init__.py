"""Structured logging for DeckBridge.

Public surface:
    configure(level, fmt)  — call once at startup
    get_logger(name)        — acquire a logger anywhere
    get_ringbuffer()        — process-wide log ringbuffer (for the M8 diagnostics WS)
"""

from deckbridge.logging_.ringbuffer import LogRingBuffer, get_ringbuffer
from deckbridge.logging_.setup import configure, get_logger

__all__ = ["LogRingBuffer", "configure", "get_logger", "get_ringbuffer"]
