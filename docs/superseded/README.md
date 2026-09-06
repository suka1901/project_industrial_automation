# Superseded files

Kept for reference, not part of the working system.

| File | Replaced by | Why |
|---|---|---|
| `socketeere.py` | `pi/` application | Course exercise leftover. Binds `192.168.125.2`, and `client_message` is unbound if `recv` returns nothing. |
| `pick_place_server.py` | `pi/main.py` | The step-2 server. Sends `move <shape>` with no coordinates and no `#` terminator, which the current robot program rejects. |
| `MainModule.mod.minimal-exercise` | `robot/MainModule.mod` | The working minimal exercise, before picking positions came from the camera. |
| `MessageParser.mod`, `PickPlace.mod` | `robot/MainModule.mod` | Written before the working robot code was available; never loaded on hardware. |
| `ServerCommuncatio.sys.original` | `ServerCommuncatio.sys` | The untouched course file. `diff` shows the one-line address change. |
