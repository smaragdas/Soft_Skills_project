from app.core.llm import llm_coach_open
import json
from colorama import init, Fore, Style
import traceback

init()  # Initialize colorama

def test_llm_response():
    try:
        print(f"{Fore.CYAN}Testing LLM Coaching Response...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Category: Leadership{Style.RESET_ALL}")
        
        # Add request debugging
        print(f"{Fore.BLUE}Sending request...{Style.RESET_ALL}")
        
        response = llm_coach_open(
            category="Leadership",
            question_id="test1",
            user_text="Όταν έχω να διαχειριστώ μια δύσκολη κατάσταση στην ομάδα, " +
                     "προσπαθώ να ακούσω όλες τις πλευρές και να βρω μια λύση " +
                     "που να ικανοποιεί όλους."
        )
        
        if not response:
            raise ValueError("Received empty response from LLM")
            
        print(f"\n{Fore.GREEN}✓ LLM Response received{Style.RESET_ALL}")
        
        # Validate response structure
        required_fields = ['keep', 'change', 'action', 'drill', 'model_name', 'score']
        missing_fields = [field for field in required_fields if field not in response]
        if missing_fields:
            raise KeyError(f"Missing required fields in response: {missing_fields}")
        
        print(f"\n{Fore.GREEN}✓ LLM Response:{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Keep:{Style.RESET_ALL} {response['keep']}")
        print(f"{Fore.WHITE}Change:{Style.RESET_ALL} {response['change']}")
        print(f"{Fore.WHITE}Action:{Style.RESET_ALL} {response['action']}")
        print(f"{Fore.WHITE}Drill:{Style.RESET_ALL} {response['drill']}")
        print(f"\n{Fore.BLUE}Model:{Style.RESET_ALL} {response['model_name']}")
        print(f"{Fore.BLUE}Score:{Style.RESET_ALL} {response['score']}")
        
    except Exception as e:
        print(f"{Fore.RED}Error occurred:{Style.RESET_ALL}")
        print(f"{Fore.RED}{str(e)}{Style.RESET_ALL}")
        print(f"{Fore.RED}Stack trace:{Style.RESET_ALL}")
        print(traceback.format_exc())

if __name__ == "__main__":
    test_llm_response()