from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import asyncio
import re
from dataclasses import dataclass
import PyPDF2
from PIL import Image
import pytesseract
from playwright.async_api import async_playwright, Browser, Page
from tasks import Task, verify_task_completion
from loop import sampling_loop

@dataclass
class TaxDocument:
    """Represents extracted tax information from a document"""
    doc_type: str  # W2, 1099-INT, 1099-DIV, etc.
    issuer: str
    tax_year: str
    fields: Dict[str, Any]  # Extracted field values
    source_file: str

@dataclass
class TaxField:
    """Represents a field to extract and enter into TurboTax"""
    name: str
    box_number: Optional[str]
    value: Any
    field_type: str = "text"  # text, currency, date, etc.
    turbotax_field_id: Optional[str] = None  # Field identifier in TurboTax

class TaxAutomation:
    def __init__(self, workflows_path: str = "tax_workflows.json", api_key: str | None = None):
        self.workflows_path = Path(workflows_path)
        self.workflows: Dict[str, List[Dict]] = self._load_workflows()
        self.api_key = api_key
        self.extracted_documents: List[TaxDocument] = []
        
    def _load_workflows(self) -> Dict[str, List[Dict]]:
        """Load existing automation workflows from file"""
        if self.workflows_path.exists():
            with open(self.workflows_path, 'r') as f:
                return json.load(f)
        return {}
    
    def save_workflow(self, task_id: str, steps: List[Dict]) -> None:
        """Save a new automation workflow"""
        self.workflows[task_id] = steps
        with open(self.workflows_path, 'w') as f:
            json.dump(self.workflows, f, indent=2)
    
    async def record_workflow(self, task_id: str, task: Optional[Task] = None) -> None:
        """Record a new workflow using Playwright or LLM completion"""
        if task:
            # Use LLM to complete the task first
            await sampling_loop(
                system_prompt_suffix="",
                messages=[{"role": "user", "content": task.description}],
                output_callback=lambda x: None,
                tool_output_callback=lambda x, y: None,
                api_response_callback=lambda x: None,
                api_key=self.api_key,
                task_description=task.description
            )
            if verify_task_completion(task):
                # Task completed by LLM, record the successful workflow
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=False)
                    page = await browser.new_page()
                    # Continue with recording
        else:
            # Traditional manual recording
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                page = await browser.new_page()
            
            # Enable request interception for recording
            await page.route("**/*", self._handle_route)
            
            # Record user actions
            steps = []
            page.on("click", lambda click: steps.append({"type": "click", "selector": click.selector}))
            page.on("fill", lambda fill: steps.append({"type": "fill", "selector": fill.selector, "value": fill.value}))
            
            # Create a completion button
            await page.evaluate("""() => {
                const button = document.createElement('button');
                button.id = 'end-recording';
                button.textContent = 'End Recording';
                button.style.position = 'fixed';
                button.style.top = '10px';
                button.style.right = '10px';
                button.style.zIndex = '10000';
                document.body.appendChild(button);
            }""")
            
            # Wait for user to click the end recording button
            try:
                await page.wait_for_selector('#end-recording', timeout=0)
                await page.click('#end-recording')
            except:
                pass
            
            await browser.close()
            
            # Save the recorded workflow
            self.save_workflow(task_id, steps)
    
    async def replay_workflow(self, task_id: str) -> bool:
        """Replay a recorded workflow"""
        if task_id not in self.workflows:
            return False
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            try:
                for step in self.workflows[task_id]:
                    if step["type"] == "click":
                        await page.click(step["selector"])
                    elif step["type"] == "fill":
                        await page.fill(step["selector"], step["value"])
                        
                await browser.close()
                return True
            except Exception as e:
                print(f"Error replaying workflow: {e}")
                await browser.close()
                return False
    
    async def _handle_route(self, route):
        """Handle request interception during recording"""
        await route.continue_()
        
    def extract_from_document(self, file_path: str) -> TaxDocument:
        """Extract tax information from a document"""
        file_path = Path(file_path)
        
        if file_path.suffix.lower() == '.pdf':
            return self._extract_from_pdf(file_path)
        elif file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            return self._extract_from_image(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    def _extract_from_pdf(self, file_path: Path) -> TaxDocument:
        """Extract tax information from PDF documents"""
        extracted_text = ""
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    extracted_text += page.extract_text()
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            
        # Determine document type
        doc_type = self._determine_document_type(extracted_text)
        
        # Extract relevant fields based on document type
        fields = self._extract_fields_for_document(extracted_text, doc_type)
        
        # Extract issuer and tax year
        issuer = self._extract_issuer(extracted_text, doc_type)
        tax_year = self._extract_tax_year(extracted_text)
        
        return TaxDocument(
            doc_type=doc_type,
            issuer=issuer,
            tax_year=tax_year,
            fields=fields,
            source_file=str(file_path)
        )
    
    def _extract_from_image(self, file_path: Path) -> TaxDocument:
        """Extract tax information from image documents using OCR"""
        try:
            image = Image.open(file_path)
            extracted_text = pytesseract.image_to_string(image)
        except Exception as e:
            print(f"Error extracting text from image: {e}")
            extracted_text = ""
            
        # Determine document type
        doc_type = self._determine_document_type(extracted_text)
        
        # Extract relevant fields based on document type
        fields = self._extract_fields_for_document(extracted_text, doc_type)
        
        # Extract issuer and tax year
        issuer = self._extract_issuer(extracted_text, doc_type)
        tax_year = self._extract_tax_year(extracted_text)
        
        return TaxDocument(
            doc_type=doc_type,
            issuer=issuer,
            tax_year=tax_year,
            fields=fields,
            source_file=str(file_path)
        )
    
    def _determine_document_type(self, text: str) -> str:
        """Determine the type of tax document based on its content"""
        if re.search(r'W-2|Wage and Tax Statement', text, re.IGNORECASE):
            return "W-2"
        elif re.search(r'1099-INT|Interest Income', text, re.IGNORECASE):
            return "1099-INT"
        elif re.search(r'1099-DIV|Dividends and Distributions', text, re.IGNORECASE):
            return "1099-DIV"
        elif re.search(r'1099-B|Proceeds from Broker', text, re.IGNORECASE):
            return "1099-B"
        elif re.search(r'1099-MISC|Miscellaneous Income', text, re.IGNORECASE):
            return "1099-MISC"
        elif re.search(r'1098|Mortgage Interest', text, re.IGNORECASE):
            return "1098"
        elif re.search(r'1098-E|Student Loan Interest', text, re.IGNORECASE):
            return "1098-E"
        elif re.search(r'1098-T|Tuition Statement', text, re.IGNORECASE):
            return "1098-T"
        elif re.search(r'1095-A|Health Insurance Marketplace', text, re.IGNORECASE):
            return "1095-A"
        else:
            return "UNKNOWN"
    
    def _extract_issuer(self, text: str, doc_type: str) -> str:
        """Extract the issuer/payer name from document"""
        if doc_type == "W-2":
            employer_match = re.search(r"(?:Employer's name.{1,5}|employer name.{1,5})([A-Za-z0-9\s,.&-]+)", text, re.IGNORECASE)
            if employer_match:
                return employer_match.group(1).strip()
        else:
            # For 1099 forms, look for payer information
            payer_match = re.search(r"(?:PAYER'S name|Payer's name).{1,5}([A-Za-z0-9\s,.&-]+)", text, re.IGNORECASE)
            if payer_match:
                return payer_match.group(1).strip()
        
        return "Unknown Issuer"
    
    def _extract_tax_year(self, text: str) -> str:
        """Extract the tax year from document"""
        year_match = re.search(r"(?:tax year|year)\s*(?:ending|ended|:)?\s*(?:in)?\s*(\d{4})", text, re.IGNORECASE)
        if year_match:
            return year_match.group(1)
        
        # Look for a standalone 4-digit year that might be the tax year
        years = re.findall(r"\b(20\d{2})\b", text)
        if years:
            # Return the most recent year (assuming it's the tax year)
            return max(years)
            
        return "Unknown Year"
    
    def _extract_fields_for_document(self, text: str, doc_type: str) -> Dict[str, Any]:
        """Extract relevant fields based on document type"""
        fields = {}
        
        if doc_type == "W-2":
            # Extract wages, federal income tax withheld, etc.
            wages_match = re.search(r"(?:Wages, tips.{1,20}|Box 1.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if wages_match:
                fields["wages"] = self._parse_currency(wages_match.group(1))
                
            fed_tax_match = re.search(r"(?:Federal income tax withheld|Box 2.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if fed_tax_match:
                fields["federal_tax_withheld"] = self._parse_currency(fed_tax_match.group(1))
                
            ss_wages_match = re.search(r"(?:Social security wages|Box 3.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if ss_wages_match:
                fields["social_security_wages"] = self._parse_currency(ss_wages_match.group(1))
                
            ss_tax_match = re.search(r"(?:Social security tax withheld|Box 4.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if ss_tax_match:
                fields["social_security_tax_withheld"] = self._parse_currency(ss_tax_match.group(1))
                
        elif doc_type == "1099-INT":
            # Extract interest income, federal income tax withheld
            interest_match = re.search(r"(?:Interest income|Box 1.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if interest_match:
                fields["interest_income"] = self._parse_currency(interest_match.group(1))
                
            fed_tax_match = re.search(r"(?:Federal income tax withheld|Box 4.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if fed_tax_match:
                fields["federal_tax_withheld"] = self._parse_currency(fed_tax_match.group(1))
                
        elif doc_type == "1099-DIV":
            # Extract dividend information
            total_div_match = re.search(r"(?:Total ordinary dividends|Box 1a.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if total_div_match:
                fields["total_ordinary_dividends"] = self._parse_currency(total_div_match.group(1))
                
            qualified_div_match = re.search(r"(?:Qualified dividends|Box 1b.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if qualified_div_match:
                fields["qualified_dividends"] = self._parse_currency(qualified_div_match.group(1))
                
            cap_gain_match = re.search(r"(?:Total capital gain distribution|Box 2a.{1,5})[^\d]*(\d+(?:[,.]\d+)?)", text, re.IGNORECASE)
            if cap_gain_match:
                fields["capital_gain_distributions"] = self._parse_currency(cap_gain_match.group(1))
        
        # Add more extraction patterns for other document types as needed
        
        return fields
    
    def _parse_currency(self, value_str: str) -> float:
        """Parse currency string to float value"""
        try:
            # Remove currency symbols, commas, etc.
            cleaned = re.sub(r'[^\d.]', '', value_str.replace(',', ''))
            return float(cleaned)
        except:
            return 0.0
            
    async def login_to_turbotax(self) -> bool:
        """Login to TurboTax using the computer automation tools"""
        # This would use the computer tools to log into TurboTax
        # Implement specific steps based on TurboTax login process
        return True
        
    async def enter_document_to_turbotax(self, document: TaxDocument) -> bool:
        """Enter extracted tax document information into TurboTax"""
        # This method would contain the logic to navigate TurboTax UI
        # and enter the extracted information
        # Implementation depends on TurboTax's UI structure
        
        # Example logic:
        # 1. Navigate to correct form section based on document type
        # 2. Enter issuer information
        # 3. Enter each field value
        # 4. Save and continue
        return True
        
    async def process_documents(self, uploaded_documents: List[str]) -> None:
        """Process a list of uploaded documents and enter data into TurboTax"""
        # Extract information from all documents
        for doc_path in uploaded_documents:
            try:
                tax_doc = self.extract_from_document(doc_path)
                self.extracted_documents.append(tax_doc)
                print(f"Successfully extracted information from {doc_path}")
            except Exception as e:
                print(f"Error processing document {doc_path}: {e}")
        
        # Log in to TurboTax
        logged_in = await self.login_to_turbotax()
        if not logged_in:
            print("Failed to log in to TurboTax")
            return
            
        # Enter each document
        for doc in self.extracted_documents:
            result = await self.enter_document_to_turbotax(doc)
            if result:
                print(f"Successfully entered {doc.doc_type} from {doc.issuer}")
            else:
                print(f"Failed to enter {doc.doc_type} from {doc.issuer}")