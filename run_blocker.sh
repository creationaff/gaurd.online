#!/bin/bash
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root to enable blocking features."
  sudo python3 one_click_block.py
else
  python3 one_click_block.py
fi
