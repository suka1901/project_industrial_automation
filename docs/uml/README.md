# UML

Class diagrams for the INA700 project, generated from the code as it stands.

Author: Suraj Karki
Course: INA700 - AI-based pick and place

| File | Shows |
|---|---|
| `01-overview.puml` | The five layers and which way dependencies point. Start here. |
| `02-domain.puml` | Value objects, enums and the pure rule modules. |
| `03-ports-vision.puml` | Camera, detector, orientation and colour ports with their adapters. |
| `04-ports-mapping-comms.puml` | Coordinate mapping, the ArUco calibrator, transport, protocol and GUI. |
| `05-application.puml` | The use cases and the selector chain. |
| `06-runtime.puml` | The four worker threads, the queues, and the shared state. |

## Rendering

```bash
plantuml -tpng *.puml       # or -tsvg for a report
```

VS Code: install the *PlantUML* extension and press `Alt+D` to preview.

## Reading them

Dependencies point **inwards only**: adapters depend on ports, use cases depend
on ports, and nothing depends on an adapter. `Container` is the single exception
and the only file that names a concrete class - which is what lets the same use
cases run against a real camera or a folder of photos.

Notation: `..|>` is realisation (a class implements a port), `-->` is
association, `*--` composition, `o--` aggregation, `..>` a dependency.
