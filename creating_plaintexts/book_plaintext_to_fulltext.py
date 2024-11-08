import os

# Define the folder containing the TXT files
input_folder = r"I:\Viesturs_workfiles\Zarins_Viltotais_Fausts_plaintexts\segments"
output_file = r"I:\Viesturs_workfiles\Zarins_Viltotais_Fausts_plaintexts\ZarM_ViltF_602888.txt"


# Metadata fields
metadata = [
    "title: Viltotais Fausts, jeb, Pārlabota un papildināta pavārgrāmata",
    "author: Zariņš, Marģeris, 1910-1993",
    "dateIssued: 1973",
    "publisher: Rīga: Liesma",
    "firstPublished: 1973",
    "firstEdition: 1973",
    "dateModified: 18.10.2024",
    "copyright:  ",
    "uri: https://dom.lndb.lv/data/obj/602888",
    "normalization: ",
    "ocrCorrection: Nē",
    "verified: "
]

# Create a list to store the combined content
combined_content = []

# Iterate through the files in the input folder
for filename in sorted(os.listdir(input_folder)):
    if filename.endswith(".txt"):
        file_path = os.path.join(input_folder, filename)

        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

            # Extract the title and content
            lines = content.splitlines()
            title_line = next((line for line in lines if line.startswith("title:")), None)
            title = title_line.split(": ", 1)[1].strip() if title_line else "Untitled"  # Keep only the title content

            # Get the content after the metadata section
            content_start_index = next((i for i, line in enumerate(lines) if line.strip() == ""), None)
            if content_start_index is not None:
                text_content = "\n".join(lines[content_start_index + 1:]).strip()
            else:
                text_content = ""

            # Append the formatted section to combined_content
            combined_content.append(f"{title}\n{text_content}")

# Write the combined content to the output file
with open(output_file, 'w', encoding='utf-8') as output:
    # Write metadata fields
    output.write("\n".join(metadata) + "\n\n")
    
    # Write each section, keeping only titles and content
    for section in combined_content:
        output.write(f"{section}\n\n")

print("Document created successfully.")