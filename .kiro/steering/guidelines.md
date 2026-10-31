# Steering Rules & Technical Constraints

- OS: Windows 11 64-bit
- GUI: PyQt6 with WA_TranslucentBackground and FramelessWindowHint
- Concurrency: Background tasks must run on QThread or daemon threads to prevent UI freezes.
- Code Style: Strict typing, comprehensive docstrings, modular FSM states.