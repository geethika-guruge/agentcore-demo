from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_grocery_list():
    c = canvas.Canvas("grocery_list.pdf", pagesize=letter)

    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "Grocery List")

    c.setFont("Helvetica", 16)
    items = [
        "2 Milk",
        "1 Bread",
        "12 Eggs",
        "5 Apples",
        "1 kg Chicken",
        "2 kg Rice",
        "6 Tomatoes",
        "500g Cheese",
        "1 Butter",
        "1 Coffee"
    ]

    y = 700
    for item in items:
        c.drawString(100, y, f"• {item}")
        y -= 30

    c.save()
    print("Created grocery_list.pdf")

if __name__ == "__main__":
    create_grocery_list()
