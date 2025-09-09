# CURRENTLY UNUSED

import os
import shutil


class FileOrganizer:
    def __init__(self, base_directory):
        self.base_directory = base_directory

    def add_file(self, file_path):
        file_name = os.path.basename(file_path)
        if len(file_name) < 2:
            raise ValueError("File name must be at least 2 characters long")

        # Create the directory structure based on the hash
        subdir = self.base_directory
        for i in range(0, len(file_name), 2):
            subdir = os.path.join(subdir, file_name[i:i+2])
            if not os.path.exists(subdir):
                os.makedirs(subdir)

            # Check if the number of files in the current directory exceeds 256
            if len(os.listdir(subdir)) < 16:
                break

        # Move the file to the appropriate directory
        destination = os.path.join(subdir, file_name)
        shutil.copy(file_path, destination)
        print(f"File {file_name} moved to {destination}")


# Example usage
if __name__ == "__main__":
    base_directory = "datastore_parma/parma_tree"
    organizer = FileOrganizer(base_directory)

    # Read all files from the parma_data directory
    parma_data_directory = "datastore_parma/parma_data"
    files_to_add = [os.path.join(parma_data_directory, f) for f in os.listdir(
        parma_data_directory) if os.path.isfile(os.path.join(parma_data_directory, f))]

    # Add files to the organizer
    for file_path in files_to_add:
        organizer.add_file(file_path)
