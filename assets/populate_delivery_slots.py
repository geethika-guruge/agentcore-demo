#!/usr/bin/env python3
"""
Populate Delivery Slots DynamoDB table with sample data
Run this script after deploying the CDK stack to initialize delivery slots
"""

import boto3
from datetime import datetime, timedelta

region = "ap-southeast-2"

# Get table name from CloudFormation outputs
cfn = boto3.client("cloudformation", region_name=region)
response = cfn.describe_stacks(StackName="OrderAssistantStack")
outputs = response["Stacks"][0]["Outputs"]
table_name = next(
    o["OutputValue"] for o in outputs if o["OutputKey"] == "DeliverySlotsTableName"
)

print(f"Using DynamoDB table: {table_name}\n")

dynamodb = boto3.resource("dynamodb", region_name=region)
table = dynamodb.Table(table_name)

# Sample delivery slots with various statuses
sample_slots = [
    {
        'slot_id': 'SLOT-20251119-001',
        'slot_date': '2025-11-19',
        'start_time': '08:00',
        'end_time': '10:00',
        'slot_capacity': 5,
        'postcode_coverage': 'SW1A',
        'slot_status': 'available',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251120-001',
        'slot_date': '2025-11-20',
        'start_time': '08:00',
        'end_time': '10:00',
        'slot_capacity': 5,
        'postcode_coverage': 'SW1A',
        'slot_status': 'available',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251203-001',
        'slot_date': '2025-12-03',
        'start_time': '08:00',
        'end_time': '10:00',
        'slot_capacity': 5,
        'postcode_coverage': 'SW1A',
        'slot_status': 'available',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251203-002',
        'slot_date': '2025-12-03',
        'start_time': '10:00',
        'end_time': '12:00',
        'slot_capacity': 5,
        'postcode_coverage': 'SW1A',
        'slot_status': 'available',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251205-001',
        'slot_date': '2025-12-05',
        'start_time': '14:00',
        'end_time': '16:00',
        'slot_capacity': 3,
        'postcode_coverage': 'EC1A',
        'slot_status': 'fully_booked',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251207-001',
        'slot_date': '2025-12-07',
        'start_time': '16:00',
        'end_time': '18:00',
        'slot_capacity': 5,
        'postcode_coverage': 'W1A',
        'slot_status': 'available',
        'is_active': True
    },
    {
        'slot_id': 'SLOT-20251210-001',
        'slot_date': '2025-12-10',
        'start_time': '12:00',
        'end_time': '14:00',
        'slot_capacity': 5,
        'postcode_coverage': 'SW1A',
        'slot_status': 'blocked',
        'is_active': False
    }
]

# Add more available slots for better testing coverage
# Start from December 3, 2025
start_date = datetime(2025, 12, 3)
additional_slots = []

# Generate slots for the next 7 days from December 3rd
for day_offset in range(7):
    slot_date = (start_date + timedelta(days=day_offset)).strftime('%Y-%m-%d')

    # Morning slot (8-10am)
    additional_slots.append({
        'slot_id': f'SLOT-{slot_date}-MORNING',
        'slot_date': slot_date,
        'start_time': '08:00',
        'end_time': '10:00',
        'slot_capacity': 10,
        'postcode_coverage': 'SW1A,SW1B,SW1C',
        'slot_status': 'available',
        'is_active': True
    })

    # Midday slot (12-2pm)
    additional_slots.append({
        'slot_id': f'SLOT-{slot_date}-MIDDAY',
        'slot_date': slot_date,
        'start_time': '12:00',
        'end_time': '14:00',
        'slot_capacity': 8,
        'postcode_coverage': 'SW1A,EC1A',
        'slot_status': 'available',
        'is_active': True
    })

    # Evening slot (5-7pm)
    additional_slots.append({
        'slot_id': f'SLOT-{slot_date}-EVENING',
        'slot_date': slot_date,
        'start_time': '17:00',
        'end_time': '19:00',
        'slot_capacity': 12,
        'postcode_coverage': 'W1A,W1B,EC1A',
        'slot_status': 'available',
        'is_active': True
    })

# Add a few fully booked and blocked slots
additional_slots.append({
    'slot_id': f'SLOT-{(start_date + timedelta(days=2)).strftime("%Y%m%d")}-BUSY',
    'slot_date': (start_date + timedelta(days=2)).strftime('%Y-%m-%d'),
    'start_time': '14:00',
    'end_time': '16:00',
    'slot_capacity': 5,
    'postcode_coverage': 'SW1A',
    'slot_status': 'fully_booked',
    'is_active': True
})

additional_slots.append({
    'slot_id': f'SLOT-{(start_date + timedelta(days=4)).strftime("%Y%m%d")}-BLOCKED',
    'slot_date': (start_date + timedelta(days=4)).strftime('%Y-%m-%d'),
    'start_time': '10:00',
    'end_time': '12:00',
    'slot_capacity': 0,
    'postcode_coverage': 'EC1A',
    'slot_status': 'blocked',
    'is_active': False
})

all_slots = sample_slots + additional_slots

print(f"Populating {len(all_slots)} delivery slots into DynamoDB table...")
print(f"Date range: {min(s['slot_date'] for s in all_slots)} to {max(s['slot_date'] for s in all_slots)}\n")

with table.batch_writer() as batch:
    for slot in all_slots:
        batch.put_item(Item=slot)
        status_emoji = "✓" if slot['slot_status'] == 'available' else "❌"
        print(f"  {status_emoji} Added: {slot['slot_date']} {slot['start_time']}-{slot['end_time']} ({slot['slot_status']})")

print(f"\n✅ Successfully populated {len(all_slots)} delivery slots!")

# Summary statistics
available_count = len([s for s in all_slots if s['slot_status'] == 'available'])
booked_count = len([s for s in all_slots if s['slot_status'] == 'fully_booked'])
blocked_count = len([s for s in all_slots if s['slot_status'] == 'blocked'])

print(f"\nSlot Status Summary:")
print(f"  - Available: {available_count} slots")
print(f"  - Fully Booked: {booked_count} slots")
print(f"  - Blocked: {blocked_count} slots")

print(f"\nPostcode Coverage:")
postcodes = set()
for slot in all_slots:
    postcodes.update(slot['postcode_coverage'].split(','))
print(f"  - {', '.join(sorted(postcodes))}")

print(f"\n💡 Use these slots for testing delivery scheduling!")
