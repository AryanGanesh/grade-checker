"""
Thapar University Grade Monitor
Autonomously checks for grade releases and sends email notifications
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('grade_monitor.log'),
        logging.StreamHandler()
    ]
)

load_dotenv()

# Configuration
INSTITUTE_USERNAME = os.getenv("INSTITUTE_USERNAME")
INSTITUTE_PASSWORD = os.getenv("INSTITUTE_PASSWORD")
INSTITUTE_URL = os.getenv("INSTITUTE_URL", "https://webkiosk.thapar.edu")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")
CHECK_INTERVAL = 45 * 60  # 45 minutes in seconds

class ThaparGradeMonitor:
    def __init__(self):
        self.driver = None
        self.wait = None
        
    def setup_driver(self):
        """Initialize Chrome browser with options"""
        logging.info("Setting up Chrome browser...")
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, 20)
        logging.info("Browser ready")
        
    def login(self):
        """Login to Thapar portal"""
        try:
            logging.info(f"Navigating to {INSTITUTE_URL}")
            self.driver.get(INSTITUTE_URL)
                
                # Wait for and fill login form
            username_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "MemberCode"))
                )
            username_field.clear()
            username_field.send_keys(INSTITUTE_USERNAME)
                
            password_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "Password"))
                )
            password_field.clear()
            password_field.send_keys(INSTITUTE_PASSWORD)

            logging.info(f"About to click submit button...")
                
            login_button = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "BTNSubmit"))
                )
            login_button.click()   
            # Verify login was successful (check for a logout link or profile name)
            self.wait.until(EC.url_contains("StudentPage.jsp"))
            logging.info("Login successful")
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False
            
    
    def navigate_to_grades(self):
        """Autonomously navigate to Student Grade Card section"""
        try:
            logging.info("Navigating to grade card section...")
            
            # Switch to leftFrame (menu)
            self.driver.switch_to.default_content()
            self.wait.until(
                EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//frame[@src='FrameLeftStudent.jsp']"))
            )
            logging.info("switch to leftFrame successful")
            
            # Expand Exam. Info. menu
            menu_list = self.wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "menutitle"))
            )
            logging.info(f"Found {len(menu_list)} elements.")

            exam_menu = menu_list[4]  # 5th element is Exam. Info
            logging.info("got exam_menu {exam_menu}")

            self.driver.execute_script("arguments[0].scrollIntoView(true);", exam_menu)
            
            # Use JavaScript to expand menu
            self.driver.execute_script("SwitchMenu('sub5')")
            
            # Wait for submenu to be visible
            self.wait.until(
                EC.visibility_of_element_located((By.ID, "sub5"))
            )
            
            # Click on Student Grade Card link
            grade_card_link = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a[title='View Event Subject Grades']")
                )
            )
            grade_card_link.click()
            
            # Switch to mainFrame/DetailSection where content loads
            self.driver.switch_to.default_content()
            self.wait.until(
                EC.frame_to_be_available_and_switch_to_it("DetailSection")
            )
            
            logging.info("Successfully navigated to grade card page")
            return True
            
        except Exception as e:
            logging.error(f"Navigation failed: {e}")
            self.driver.save_screenshot("navigation_error.png")
            return False
    
    def select_semester_and_subject(self):
        """Select semester and subject, then trigger Show"""
        try:
            logging.info("Selecting semester and subject...")
            
            # Wait for exam dropdown to be present
            exam_dropdown = self.wait.until(
                EC.presence_of_element_located((By.ID, "exam"))
            )
            
            # Select semester using Select class
            semester_select = Select(exam_dropdown)
            semester_select.select_by_value("2526ODDSEM")
            logging.info("Selected semester: 2526ODDSEM")
            
            # Check if subject dropdown exists
            # try:
            #     subject_dropdown = self.wait.until(
            #         EC.presence_of_element_located((By.ID, "subject")),
            #         timeout=5
            #     )
            #     subject_select = Select(subject_dropdown)
            #     subject_select.select_by_value("ALL")
            #     logging.info("Selected subject: ALL")
            # except TimeoutException:
            #     logging.info("Subject dropdown not found, continuing...")
            
            # Click Show button
            show_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@value='Show']"))
            )
            logging.info("Show button found, submitting form...")
            show_button.click()
            
            time.sleep(2)
            # Wait for page to process
            # self.wait.until(
            #     EC.staleness_of(show_button)
            # )
            
            logging.info("Form submitted successfully")
            return True
            
        except Exception as e:
            logging.error(f"Form submission failed: {e}")
            self.driver.save_screenshot("form_error.png")
            return False
    
    def check_grade_status(self):
        """
        Check if grades are released
        Returns: (grades_available: bool, data: dict or str)
        """
        try:
            logging.info("Checking grade status...")
            
            # Wait a moment for page to load
            time.sleep(2)
            
            # Check for "no results" messages
            page_source = self.driver.page_source.lower()
            
            if any(msg in page_source for msg in [
                'result not found',
                'no record found',
                'grades not available',
                'not declared',
                'अभी परिणाम घोषित नहीं',
                'This data is for information only and can be authenticated by the Academic Section, TU. In case of discrepancy, please contact AR(Academic),TU.'
            ]):
                logging.info("Grades not yet available - found 'not available' message")
                return False, "Grades not yet released"
            
            # Look for red alert or error messages
            # try:
            #     alert_element = self.driver.find_element(
            #         By.CSS_SELECTOR, 
            #         "div[style*='color:red'], .alert-danger, font[color='red']"
            #     )
            #     if alert_element.is_displayed():
            #         alert_text = alert_element.text.strip()
            #         logging.info(f"Alert found: {alert_text}")
            #         return False, alert_text
            # except NoSuchElementException:
            #     pass
            
            # Look for grade table - multiple possible IDs/classes
            grade_table = self.driver.find_elements(By.ID, "table-1")
            logging.info(f"Found {len(grade_table)} tables on the page.")

            if grade_table:
                # table_content = grade_table[0].get_attribute('innerHTML')
                # logging.info(f"content of table: {table_content}")

                rows = grade_table[0].find_elements(By.TAG_NAME, "tbody tr")
                logging.info(f"Found {len(rows)} rows in the grade table.")

                if len(rows) <= 0:
                    logging.info("Table body is empty, no grades found")
                    return False, "Grade table is empty"

                logging.info("✓ GRADES FOUND! Table with grade data detected")
                grade_data = self.extract_grade_data(grade_table[0])

                logging.info("Data: {}".format(grade_data))
                return True, grade_data
            else:
                logging.info("No table with ID 'table-1' found, checking other selectors...")   
                return False, "Grade table not found"
            
        except Exception as e:
            logging.error(f"Error checking grade status: {e}")
            self.driver.save_screenshot("status_check_error.png")
            return False, str(e)
    
    def extract_grade_data(self, table):
        """Extract structured data from grade table"""
        try:
            data = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'subjects': []
            }
            
            rows = table.find_elements(By.TAG_NAME, "tr")
            
            # Get headers
            headers = []
            header_row = rows[0]
            header_cells = header_row.find_elements(By.TAG_NAME, "th")
            if not header_cells:
                header_cells = header_row.find_elements(By.TAG_NAME, "td")
            
            for cell in header_cells:
                headers.append(cell.text.strip())
            
            data['headers'] = headers
            
            # Get data rows
            for row in rows[1:]:
                cells = row.find_elements(By.TAG_NAME, "td")
                if cells and len(cells) >= 2:
                    row_data = [cell.text.strip() for cell in cells]
                    if any(row_data):  # Only add non-empty rows
                        data['subjects'].append(row_data)
            
            logging.info(f"Extracted {len(data['subjects'])} grade entries")
            return data
            
        except Exception as e:
            logging.error(f"Error extracting grade data: {e}")
            return {'error': str(e)}
    
    def format_grade_email(self, grade_data):
        """Format grade data into HTML email"""
        if isinstance(grade_data, str):
            return f"<p>{grade_data}</p>"
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
                td {{ border: 1px solid #ddd; padding: 10px; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .timestamp {{ color: #7f8c8d; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <h2>🎓 Thapar University - Grades Released!</h2>
            <p class="timestamp">Checked at: {grade_data.get('timestamp', 'N/A')}</p>
            <table>
                <tr>
                    {''.join(f'<th>{h}</th>' for h in grade_data.get('headers', []))}
                </tr>
        """
        
        for subject in grade_data.get('subjects', []):
            html += "<tr>"
            html += ''.join(f'<td>{cell}</td>' for cell in subject)
            html += "</tr>"
        
        html += """
            </table>
            <p><em>This is an automated notification from your grade monitoring script.</em></p>
        </body>
        </html>
        """
        
        return html
    
    def send_email_notification(self, grade_data):
        """Send email notification with grade data"""
        try:
            logging.info("Sending email notification...")
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = '🎓 Thapar Grades Released - Check Your Results!'
            msg['From'] = EMAIL_FROM
            msg['To'] = EMAIL_TO
            
            # Plain text version
            text = "Your grades have been released! Check the portal for details."
            
            # HTML version
            html = self.format_grade_email(grade_data)
            
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email using Gmail SMTP
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
            
            logging.info(f"✓ Email sent successfully to {EMAIL_TO}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False
    
    def monitor_grades(self):
        """Main monitoring loop"""
        attempt = 0
        
        while True:
            try:
                attempt += 1
                logging.info(f"{'='*60}")
                logging.info(f"Grade Check Attempt #{attempt}")
                logging.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info(f"{'='*60}")
                
                # Navigate to grades page
                if not self.navigate_to_grades():
                    logging.error("Navigation failed, retrying in 5 minutes...")
                    time.sleep(300)
                    continue
                
                # Submit form
                if not self.select_semester_and_subject():
                    logging.error("Form submission failed, retrying...")
                    time.sleep(60)
                    continue
                
                # Check grade status
                grades_available, data = self.check_grade_status()
                
                if grades_available:
                    logging.info("🎉 GRADES ARE AVAILABLE!")
                    
                    # Send email notification
                    if self.send_email_notification(data):
                        logging.info("Notification sent successfully")
                    
                    # Save screenshot
                    self.driver.save_screenshot(
                        f"grades_released_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    
                    logging.info("Monitoring complete - grades found!")
                    break
                else:
                    logging.info(f"Status: {data}")
                    logging.info(f"Next check in {CHECK_INTERVAL // 60} minutes...")
                    time.sleep(CHECK_INTERVAL)
                    
            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
                self.driver.save_screenshot(f"error_{attempt}.png")
                logging.info("Waiting 5 minutes before retry...")
                time.sleep(300)
    
    def run(self):
        """Main entry point"""
        try:
            self.setup_driver()
            
            if not self.login():
                logging.error("Login failed - exiting")
                return
            
            self.monitor_grades()
            
        except KeyboardInterrupt:
            logging.info("\nMonitoring stopped by user")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
        finally:
            if self.driver:
                #logging.info("Keeping browser open for 10 seconds...")
                #time.sleep(10)
                self.driver.quit()
                logging.info("Browser closed")

def main():
    """Main function"""
    # Validate configuration
    if not all([INSTITUTE_USERNAME, INSTITUTE_PASSWORD, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        print("❌ Error: Missing required environment variables!")
        print("\nRequired in .env file:")
        print("  INSTITUTE_USERNAME=your_username")
        print("  INSTITUTE_PASSWORD=your_password")
        print("  INSTITUTE_URL=https://webkiosk.thapar.edu")
        print("  EMAIL_FROM=your_email@gmail.com")
        print("  EMAIL_PASSWORD=your_gmail_app_password")
        print("  EMAIL_TO=recipient@email.com")
        return
    
    logging.info("="*60)
    logging.info("Thapar University Grade Monitor Starting")
    logging.info("="*60)
    logging.info(f"Username: {INSTITUTE_USERNAME}")
    logging.info(f"Portal: {INSTITUTE_URL}")
    logging.info(f"Check interval: {CHECK_INTERVAL // 60} minutes")
    logging.info(f"Notification email: {EMAIL_TO}")
    logging.info("="*60 + "\n")
    
    monitor = ThaparGradeMonitor()
    monitor.run()

if __name__ == "__main__":
    main()