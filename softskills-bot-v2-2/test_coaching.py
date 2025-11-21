from app.core.llm import llm_coach_open

def test_coaching_response():
    try:
        response = llm_coach_open(
            category="Communication",
            question_id="test_q1",
            user_text="Όταν πρέπει να επικοινωνήσω κάτι σημαντικό στην ομάδα, προετοιμάζω τα κύρια σημεία και προσπαθώ να είμαι σαφής."
        )
        
        print("\nCoaching Response:")
        print("Keep:", response["keep"])
        print("Change:", response["change"])
        print("Action:", response["action"])
        print("Drill:", response["drill"])
        print("Model:", response["model_name"])
        
    except Exception as e:
        print(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_coaching_response()