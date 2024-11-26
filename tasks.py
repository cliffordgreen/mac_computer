from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class Task:
    description: str
    completion_criteria: str
    required_credentials: List[str]
    downloaded_file: Optional[str] = None
    start_time: float = 0.0
    verification_requested: bool = False 

    
PREDEFINED_TASKS = [
    Task(
        description="use chrome (only chrome ) and to navigate to wealthfront login, from there use the test credentials should already be save there, even if you can't see the password assume its autofilled then download the available 1099s. In wealthfront you will click the download button, then you will be prompted with options for PDF or EXCEL, Click the PDF icon. Ensure you click the download PDF button and that a download had started. Confirm the download by looking in the Downloads folder for the downloaded file. Assume the task is complete once confirmed and move to next task",
        completion_criteria="1099 file downloaded in Downloads folder",
        required_credentials=["email"]
    ),
    Task(
        description="use chrome (only chrome ), assume you need to open a new tab, and to navigate to Etrade login, from there use the test credentials should already be saved there and let it autofill, even if you can't see the password assume its autofilled. If you hit a verifcation step, assume the number is correct and have the website send the code. then download the available 1099s. Confirm the 1099 is download by looking in the Downloads folder. IF youre asked for a code, have them send it and i will provide it to you! youre the best and you can do this! please dont make mistakes",
        completion_criteria="1099 file downloaded in Downloads folder",
        required_credentials=["verification_code"]
    ),
    Task(
        description="use chrome (only chrome)  assume you need to open a new tab, and to navigate to airbnb login, from there use these test credentials to airbnb {email: cliff.r.green@gmail.com, password: ********, phone number: 8583612144} , airbnb will text a code and you can pull the code form the messages app to finish login, then download the available 1099s",
        completion_criteria="1099 file downloaded in Downloads folder or confirmed no forms available",
        required_credentials=[ "phone_number"]
    )
]

def verify_task_completion(task: Task) -> bool:
    """
    Verify if a task has been completed based on its completion criteria
    """
    downloads_dir = Path.home() / "Downloads"
    
    if "1099" in task.completion_criteria:
        # Check for recently downloaded 1099 files
        recent_files = [f for f in downloads_dir.glob("*1099*.pdf") if f.stat().st_mtime > task.start_time]
        if recent_files:
            task.downloaded_file = str(recent_files[0])
            return True
    
    return False