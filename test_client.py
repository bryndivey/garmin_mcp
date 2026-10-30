#!/usr/bin/env python3
"""Test MCP client for debugging the Garmin MCP server"""

import asyncio
import logging
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import mcp.types as types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_client")

async def test_mcp_server():
    url = "https://garmin-mcp-server-459967316618.us-central1.run.app/mcp"
    
    # Test with streamable HTTP client
    async with streamablehttp_client(url) as (read_stream, write_stream, get_session_id):
        async with ClientSession(
            read_stream,
            write_stream,
            client_info=types.Implementation(name="test-client", version="1.0.0")
        ) as session:
            logger.info("Initializing session...")
            result = await session.initialize()
            logger.info(f"Initialized: {result}")
            
            logger.info("Listing tools...")
            tools = await session.list_tools()
            logger.info(f"Found {len(tools.tools)} tools")
            
            for tool in tools.tools:
                logger.info(f"Tool: {tool.name} - {tool.description}")
            
            # Test listing activities and get detailed weight training info
            logger.info("Getting recent activities...")
            try:
                activities_result = await session.call_tool("list_activities", {"limit": 10})
                logger.info(f"Activities list: {activities_result}")
                
                # Parse the activities to extract IDs and find latest strength training
                activities_text = activities_result.content[0].text
                
                # Extract activity info (ID and type)
                import re
                activity_blocks = re.findall(r'--- Activity \d+ ---\n.*?Type: ([^\n]+)\n.*?ID: (\d+)', activities_text, re.DOTALL)
                
                # Find the latest strength training activity
                latest_strength_id = None
                for activity_type, activity_id in activity_blocks:
                    if 'strength' in activity_type.lower():
                        latest_strength_id = int(activity_id)
                        logger.info(f"Found latest strength training activity: {latest_strength_id}")
                        break
                
                if latest_strength_id:
                    # Get exercise sets for the latest strength training
                    logger.info(f"Getting exercise sets for strength training {latest_strength_id}...")
                    try:
                        exercise_sets_result = await session.call_tool("get_activity_exercise_sets", {"activity_id": latest_strength_id})
                        exercise_sets_text = exercise_sets_result.content[0].text
                        
                        # Parse and display the exercise sets in a readable format
                        import json
                        exercise_data = json.loads(exercise_sets_text)
                        
                        logger.info("=== DETAILED WORKOUT BREAKDOWN ===")
                        logger.info(f"Activity ID: {exercise_data['activityId']}")
                        
                        active_sets = [s for s in exercise_data['exerciseSets'] if s['setType'] == 'ACTIVE']
                        rest_sets = [s for s in exercise_data['exerciseSets'] if s['setType'] == 'REST']
                        
                        logger.info(f"Total Sets: {len(exercise_data['exerciseSets'])}")
                        logger.info(f"Active Sets: {len(active_sets)}")
                        logger.info(f"Rest Periods: {len(rest_sets)}")
                        logger.info("")
                        
                        # Group exercises by type for better readability
                        exercise_groups = {}
                        for i, exercise_set in enumerate(active_sets):
                            if exercise_set['exercises']:
                                exercise_name = exercise_set['exercises'][0]['category']
                                specific_name = exercise_set['exercises'][0].get('name', 'Generic')
                            else:
                                exercise_name = "UNKNOWN"
                                specific_name = "Unknown Exercise"
                            
                            if exercise_name not in exercise_groups:
                                exercise_groups[exercise_name] = []
                            
                            exercise_groups[exercise_name].append({
                                'set_number': i + 1,
                                'specific_name': specific_name,
                                'reps': exercise_set.get('repetitionCount'),
                                'weight': exercise_set.get('weight'),
                                'duration': exercise_set.get('duration'),
                                'start_time': exercise_set.get('startTime'),
                                'probability': exercise_set['exercises'][0].get('probability', 0) if exercise_set['exercises'] else 0
                            })
                        
                        # Display grouped exercises
                        for exercise_type, sets in exercise_groups.items():
                            logger.info(f"=== {exercise_type.replace('_', ' ').title()} ===")
                            for set_info in sets:
                                weight_kg = set_info['weight'] / 1000 if set_info['weight'] and set_info['weight'] > 0 else None
                                weight_str = f"{weight_kg:.1f}kg" if weight_kg else "Bodyweight" if set_info['weight'] == -1 else "No weight"
                                
                                reps_str = f"{set_info['reps']} reps" if set_info['reps'] else "No reps"
                                duration_str = f"{set_info['duration']:.1f}s" if set_info['duration'] else "No duration"
                                time_str = set_info['start_time'].split('T')[1].split('.')[0] if set_info['start_time'] else "Unknown time"
                                
                                exercise_name = set_info['specific_name'].replace('_', ' ').title() if set_info['specific_name'] and set_info['specific_name'] != 'Generic' else exercise_type.replace('_', ' ').title()
                                confidence = f"({set_info['probability']:.1f}% confidence)" if set_info['probability'] > 0 else ""
                                
                                logger.info(f"  Set {set_info['set_number']}: {exercise_name} - {reps_str}, {weight_str}, {duration_str} @ {time_str} {confidence}")
                            logger.info("")
                        
                        # Summary statistics
                        total_reps = sum(s.get('repetitionCount', 0) for s in active_sets if s.get('repetitionCount'))
                        total_weight_moved = sum(
                            (s.get('repetitionCount', 0) * s.get('weight', 0)) / 1000 
                            for s in active_sets 
                            if s.get('repetitionCount') and s.get('weight') and s.get('weight') > 0
                        )
                        total_duration = sum(s.get('duration', 0) for s in active_sets)
                        
                        logger.info("=== WORKOUT SUMMARY ===")
                        logger.info(f"Total Reps: {total_reps}")
                        logger.info(f"Total Weight Moved: {total_weight_moved:.1f}kg")
                        logger.info(f"Total Active Time: {total_duration/60:.1f} minutes")
                        logger.info(f"Exercise Types: {len(exercise_groups)}")
                        
                    except Exception as e:
                        logger.error(f"Failed to get exercise sets for activity {latest_strength_id}: {e}")
                else:
                    logger.info("No strength training activities found in recent activities")
                        
            except Exception as e:
                logger.error(f"Activity analysis failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_server())