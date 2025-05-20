import re
import os

def clean_code_block_content(code_str):
    """
    Removes the outer ``` and strips whitespace if the block is multi-line.
    For single-line code not in ```, it just strips.
    """
    if isinstance(code_str, str):
        stripped_code = code_str.strip()
        if stripped_code.startswith("```") and stripped_code.endswith("```"):
            cleaned = stripped_code[3:-3]
            return cleaned.strip()
        return stripped_code
    return code_str

def split_respecting_quotes_and_backticks(text, delimiter=',', max_splits=-1):
    """
    Splits a string by a delimiter, respecting fields enclosed in
    double quotes (") or triple backticks (```).
    Handles escaped quotes ("") inside double-quoted fields.
    """
    parts = []
    current_part = []
    in_double_quotes = False
    in_triple_backticks = False
    i = 0
    n = len(text)
    splits_done = 0

    while i < n:
        # Check for triple backticks first as they are more distinct
        if text[i:i+3] == '```':
            current_part.append('```')
            in_triple_backticks = not in_triple_backticks
            i += 3
            continue

        char = text[i]

        if not in_triple_backticks: # Only process quotes if not inside backticks
            if char == '"':
                # Handle CSV-style escaped quotes: "" inside a quoted field becomes "
                if in_double_quotes and i + 1 < n and text[i+1] == '"':
                    current_part.append('"') # Add one quote
                    i += 1 # Skip the second quote of the escape pair
                else:
                    in_double_quotes = not in_double_quotes
                current_part.append(char) # Still include the quote character itself
                i += 1
                continue

        if char == delimiter and not in_double_quotes and not in_triple_backticks:
            if max_splits == -1 or splits_done < max_splits:
                parts.append("".join(current_part))
                current_part = []
                splits_done += 1
            else: # Max splits reached, append the rest of the string
                current_part.append(char)
        else:
            current_part.append(char)
        i += 1

    parts.append("".join(current_part)) # Add the last part
    return parts


def _process_record_buffer_for_stream(record_lines_buffer, filter_person_name, record_start_line_num):
    """
    Internal helper to process a buffered record and return it if it matches the filter.
    Called by stream_filtered_records.
    """
    if not record_lines_buffer:
        return None

    full_record_text = "\n".join(record_lines_buffer)

    try:
        parts = split_respecting_quotes_and_backticks(full_record_text, delimiter=',', max_splits=6)

        if len(parts) < 7:
            print(f"Warning (Line ~{record_start_line_num}): Could not split record into 7 main fields. Got {len(parts)}. Skipping.")
            # print(f"Content hint: {full_record_text[:200]}...")
            return None

        rec_id = parts[0].strip()
        person_in_charge = parts[1].strip()
        question_raw = parts[4].strip()
        prepre_code_raw = parts[5].strip()
        run_code_raw = parts[6].strip()

        if person_in_charge != filter_person_name:
            return None # Does not match filter

        if question_raw.startswith('"') and question_raw.endswith('"'):
            question_cleaned = question_raw[1:-1].replace('""', '"')
        else:
            question_cleaned = question_raw

        return {
            "id": rec_id,
            "负责人": person_in_charge,
            "question": question_cleaned,
            "prepareCode": clean_code_block_content(prepre_code_raw),
            "runCode": clean_code_block_content(run_code_raw)
        }
    except Exception as e:
        print(f"Error processing record starting line {record_start_line_num}: {e}")
        # print(f"Problematic buffer content:\n" + "\n".join(record_lines_buffer))
        return None
    
def process_buffered_record(record_lines_buffer, all_records, filter_person_name, record_start_line_num):
    if not record_lines_buffer:
        return

    full_record_text = "\n".join(record_lines_buffer)

    # Split the full record text into its 7 main logical columns
    # id,负责人,是否完成,函数,问题,prepreCode,runCode
    # We want 6 splits to get 7 parts.
    try:
        # The first split should reliably give us the ID based on the regex
        parts = split_respecting_quotes_and_backticks(full_record_text, delimiter=',', max_splits=6)

        if len(parts) < 7: # Expecting 7 fields after 6 splits
            print(f"Warning: Record starting line {record_start_line_num} - "
                  f"Could not split into enough main fields (expected 7, got {len(parts)}). Skipping.")
            print(f"Problematic content: {full_record_text[:200]}...") # Print start of problematic content
            return

        rec_id = parts[0].strip()
        person_in_charge = parts[1].strip()
        # status_complete = parts[2].strip() # unused for now
        # function_name = parts[3].strip()   # unused for now
        question_raw = parts[4].strip()
        prepre_code_raw = parts[5].strip()
        run_code_raw = parts[6].strip()

        # Filter by "负责人"
        if person_in_charge != filter_person_name:
            return

        # Clean quotes from the "问题" field if it's quoted
        # A simple strip('"') might be too naive if quotes are part of content
        # but for CSV-like quoting, it's common.
        if question_raw.startswith('"') and question_raw.endswith('"'):
            question_cleaned = question_raw[1:-1].replace('""', '"') # Handle escaped quotes
        else:
            question_cleaned = question_raw

        all_records.append({
            "id": rec_id,
            "负责人": person_in_charge,
            "question": question_cleaned,
            "prepareCode": clean_code_block_content(prepre_code_raw),
            "runCode": clean_code_block_content(run_code_raw)
        })

    except Exception as e:
        print(f"Error processing record starting line {record_start_line_num}: {e}")
        print(f"Problematic buffer content:\n" + "\n".join(record_lines_buffer))

# --- Main Generator Function ---
def stream_filtered_records(filepath, filter_person_name):
    """
    Parses the custom multi-line format and yields filtered records one by one.

    Args:
        filepath (str): The path to the custom data file.
        filter_person_name (str): The name of the "负责人" to filter by.

    Yields:
        dict: A dictionary representing a parsed and filtered record, containing
              keys: "id", "负责人", "question", "prepareCode", "runCode".
              Yields nothing if the file is not found or on parsing errors for a record.
    """
    record_start_regex = re.compile(r"^\d+,") # Assumes ID is numeric

    if not os.path.exists(filepath):
        print(f"Error: File not found at {filepath}")
        return # Or raise FileNotFoundError

    buffer = []
    line_number_start_of_buffer = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num_file, line_content in enumerate(f, 1):
            line_content = line_content.rstrip('\n')

            if record_start_regex.match(line_content) and buffer:
                # Process the previous buffer and yield if it matches
                processed_record = _process_record_buffer_for_stream(
                    buffer, filter_person_name, line_number_start_of_buffer
                )
                if processed_record:
                    yield processed_record
                buffer = [line_content]
                line_number_start_of_buffer = line_num_file
            else:
                if not buffer:
                    line_number_start_of_buffer = line_num_file
                buffer.append(line_content)

        # Process the last record in the buffer
        if buffer:
            processed_record = _process_record_buffer_for_stream(
                buffer, filter_person_name, line_number_start_of_buffer
            )
            if processed_record:
                yield processed_record

