#!/usr/bin/env python3
import aws_cdk as cdk
from stack import OrderAssistantStack


app = cdk.App()
OrderAssistantStack(app, "OrderAssistantStack")

app.synth()
