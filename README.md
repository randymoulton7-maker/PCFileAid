PCFileAid is a Python-based utility designed to help mainframe developers, analysts, and support engineers work efficiently with copybooks, fixed‑width layouts, and EBCDIC-derived data files. It provides a simple, operator‑style interface for parsing, inspecting, and converting structured data used in z/OS environments.
Overview
PCFileAid is built to replicate and modernize common mainframe file inspection workflows on a Windows workstation. It supports:
Parsing COBOL copybooks
Generating fixed‑width layout definitions
Inspecting and validating input data
Converting structured text into usable Python objects
Providing a foundation for future GUI enhancements using Tkinter
The project is intended to be modular, allowing additional tools and utilities to be added over time.
Features
Copybook Parsing
Reads COBOL copybook definitions
Extracts field names, positions, and lengths
Produces layout metadata for downstream processing
Layout Generation
Converts copybook metadata into .fad or fixed‑width layout formats
Ensures alignment with mainframe-style column numbering
Data Inspection
Reads structured text files
Applies layout definitions to extract fields
Supports debugging malformed or misaligned records
Tkinter Integration
Provides a foundation for GUI-based tools
Allows future expansion into a full PC-based FileAid utility
File Structure
The repository currently contains:
pcfileaid.py — Main program logic and Tkinter framework
copybook_to_layout.py — Copybook parsing and layout generation tool
copybook_input_data.txt — Sample input data for testing
Additional modules and documentation will be added as the project evolves.
Usage
Run the main program:
python pcfileaid.py
Use the layout generator:
python copybook_to_layout.py
Input files can be placed in the same directory or referenced by full path.
Requirements
Python 3.10+
Tkinter (included with standard Python installations)
Roadmap
Planned enhancements include:
GUI-based copybook viewer
EBCDIC-to-ASCII conversion utilities
Integrated record editor
Support for multiple layout formats
Export to CSV, JSON, and other structured formats
License
This project is maintained privately by the author. Licensing will be defined when the project is made public.

Author
Developed by Randy Moulton.
For questions or contributions, please contact the repository owner.
