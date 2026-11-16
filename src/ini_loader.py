"""
Reads settings.ini into section -> (key -> value). Values are strings, except
"List:a|b|c" (a list of trimmed strings) and "Map:k:v|k2:v2" (a dict of strings).
Lines starting with ';' are comments. A line with more than one '=' gets an empty value.
"""


def java_split(s, sep):
    """String.split as Java does it: trailing empty pieces are dropped."""
    if s == "":
        return [""]
    parts = s.split(sep)
    while parts and parts[-1] == "":
        parts.pop()
    return parts


class IniLoader:
    def __init__(self, path):
        self.ini_file = path

    def load(self):
        file_data = {}
        category = "uncategorized"

        with open(self.ini_file) as ini_reader:
            for line in ini_reader:
                line = line.strip()
                if line.startswith(";"):
                    continue

                if line.startswith("["):
                    category = line.replace("[", "").replace("]", "")
                elif "=" in line:
                    if category not in file_data:
                        file_data[category] = {}

                    parts = java_split(line, "=")
                    key = parts[0].strip()
                    value = (parts[1] if len(parts) == 2 else "").strip()

                    if value.startswith("List:"):
                        value = value.replace("List:", "")
                        parsed = [s.strip() for s in java_split(value, "|")]
                    elif value.startswith("Map:"):
                        value = value.replace("Map:", "")
                        parsed = {}
                        for entry in java_split(value, "|"):
                            key_value = java_split(entry, ":")
                            parsed[key_value[0].strip()] = key_value[1].strip()
                    else:
                        parsed = value
                    file_data[category][key] = parsed
        return file_data
