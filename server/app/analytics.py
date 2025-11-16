"""
Analytics Module for Admin Feedback System.

This module provides analytics and metrics for conversation quality,
feedback trends, and bot improvement over time.
"""

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from azure.storage.blob.aio import BlobServiceClient

logger = logging.getLogger(__name__)


class Analytics:
    """
    Provides analytics for conversations and feedback.
    
    Features:
    - Conversation metrics (count, duration, turns)
    - Feedback statistics (ratings, tags)
    - Quality trends over time
    - PII detection statistics
    - Improvement tracking
    """
    
    def __init__(self, storage_connection_string: str):
        """
        Initialize analytics module.
        
        Args:
            storage_connection_string: Azure Storage connection string
        """
        self.storage_connection_string = storage_connection_string
        self.blob_service_client = None
    
    async def initialize(self):
        """Initialize Azure Storage client."""
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.storage_connection_string
        )
        logger.info("Analytics module initialized")
    
    async def get_conversation_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get summary statistics for conversations.
        
        Args:
            start_date: Filter conversations from this date
            end_date: Filter conversations until this date
            
        Returns:
            Dictionary with conversation statistics
        """
        try:
            conversations_container = self.blob_service_client.get_container_client("conversations")
            
            stats = {
                "total_conversations": 0,
                "total_turns": 0,
                "avg_turns_per_conversation": 0,
                "total_duration_seconds": 0,
                "avg_duration_seconds": 0,
                "by_channel": {"web": 0, "phone": 0, "unknown": 0},
                "pii_detected": {
                    "conversations_with_pii": 0,
                    "pii_types": Counter()
                },
                "search_usage": {
                    "conversations_with_search": 0,
                    "total_searches": 0
                }
            }
            
            async for blob in conversations_container.list_blobs():
                # Filter by date if specified
                if start_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < start_date:
                    continue
                if end_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) > end_date:
                    continue
                
                # Download and parse conversation
                blob_client = conversations_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                conv = json.loads(await content.readall())
                
                # Update stats
                stats["total_conversations"] += 1
                stats["total_turns"] += len(conv.get("turns", []))
                stats["total_duration_seconds"] += conv.get("metadata", {}).get("duration_seconds", 0)
                
                channel = conv.get("channel", "unknown")
                stats["by_channel"][channel] = stats["by_channel"].get(channel, 0) + 1
                
                # PII statistics
                pii_types = conv.get("pii_detected_types", [])
                if pii_types:
                    stats["pii_detected"]["conversations_with_pii"] += 1
                    for pii_type in pii_types:
                        stats["pii_detected"]["pii_types"][pii_type] += 1
                
                # Search usage
                search_used = any(turn.get("search_used", False) for turn in conv.get("turns", []))
                if search_used:
                    stats["search_usage"]["conversations_with_search"] += 1
                    stats["search_usage"]["total_searches"] += sum(
                        1 for turn in conv.get("turns", []) if turn.get("search_used", False)
                    )
            
            # Calculate averages
            if stats["total_conversations"] > 0:
                stats["avg_turns_per_conversation"] = round(
                    stats["total_turns"] / stats["total_conversations"], 2
                )
                stats["avg_duration_seconds"] = round(
                    stats["total_duration_seconds"] / stats["total_conversations"], 2
                )
            
            # Convert Counter to dict
            stats["pii_detected"]["pii_types"] = dict(stats["pii_detected"]["pii_types"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting conversation summary: {e}")
            return {}
    
    async def get_feedback_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get summary statistics for feedback.
        
        Args:
            start_date: Filter feedback from this date
            end_date: Filter feedback until this date
            
        Returns:
            Dictionary with feedback statistics
        """
        try:
            feedback_container = self.blob_service_client.get_container_client("feedback")
            
            stats = {
                "total_feedback": 0,
                "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "avg_rating": 0,
                "approved_count": 0,
                "tag_distribution": Counter(),
                "most_common_issues": []
            }
            
            total_rating = 0
            
            async for blob in feedback_container.list_blobs():
                # Filter by date if specified
                if start_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) < start_date:
                    continue
                if end_date and blob.creation_time and blob.creation_time.replace(tzinfo=timezone.utc) > end_date:
                    continue
                
                # Download and parse feedback
                blob_client = feedback_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                feedback = json.loads(await content.readall())
                
                # Update stats
                stats["total_feedback"] += 1
                
                rating = feedback.get("rating", 0)
                if 1 <= rating <= 5:
                    stats["rating_distribution"][rating] += 1
                    total_rating += rating
                
                if feedback.get("approved", False):
                    stats["approved_count"] += 1
                
                # Tag statistics
                for tag in feedback.get("tags", []):
                    stats["tag_distribution"][tag] += 1
            
            # Calculate average rating
            if stats["total_feedback"] > 0:
                stats["avg_rating"] = round(total_rating / stats["total_feedback"], 2)
            
            # Get most common issues (tags)
            stats["most_common_issues"] = [
                {"tag": tag, "count": count}
                for tag, count in stats["tag_distribution"].most_common(10)
            ]
            
            # Convert Counter to dict
            stats["tag_distribution"] = dict(stats["tag_distribution"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting feedback summary: {e}")
            return {}
    
    async def get_quality_trends(
        self,
        days: int = 30,
        interval_days: int = 7
    ) -> Dict:
        """
        Get quality trends over time.
        
        Args:
            days: Number of days to analyze
            interval_days: Interval for grouping (e.g., weekly = 7)
            
        Returns:
            Dictionary with trend data
        """
        try:
            feedback_container = self.blob_service_client.get_container_client("feedback")
            
            # Calculate date ranges
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            # Group feedback by intervals
            intervals = defaultdict(lambda: {"count": 0, "total_rating": 0, "ratings": []})
            
            async for blob in feedback_container.list_blobs():
                if not blob.creation_time:
                    continue
                
                blob_date = blob.creation_time.replace(tzinfo=timezone.utc)
                if blob_date < start_date or blob_date > end_date:
                    continue
                
                # Download feedback
                blob_client = feedback_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                feedback = json.loads(await content.readall())
                
                # Determine interval
                days_from_start = (blob_date - start_date).days
                interval_key = (days_from_start // interval_days) * interval_days
                interval_date = start_date + timedelta(days=interval_key)
                interval_str = interval_date.strftime("%Y-%m-%d")
                
                # Update interval stats
                rating = feedback.get("rating", 0)
                if 1 <= rating <= 5:
                    intervals[interval_str]["count"] += 1
                    intervals[interval_str]["total_rating"] += rating
                    intervals[interval_str]["ratings"].append(rating)
            
            # Calculate averages for each interval
            trend_data = []
            for date_str in sorted(intervals.keys()):
                data = intervals[date_str]
                avg_rating = data["total_rating"] / data["count"] if data["count"] > 0 else 0
                trend_data.append({
                    "date": date_str,
                    "feedback_count": data["count"],
                    "avg_rating": round(avg_rating, 2)
                })
            
            return {
                "period_days": days,
                "interval_days": interval_days,
                "trends": trend_data
            }
            
        except Exception as e:
            logger.error(f"Error getting quality trends: {e}")
            return {}
    
    async def get_approved_responses_stats(self) -> Dict:
        """Get statistics for approved responses."""
        try:
            approved_container = self.blob_service_client.get_container_client("approved-responses")
            
            stats = {
                "total_approved": 0,
                "by_rating": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
                "by_tag": Counter(),
                "most_used": []
            }
            
            approved_responses = []
            
            async for blob in approved_container.list_blobs():
                blob_client = approved_container.get_blob_client(blob.name)
                content = await blob_client.download_blob()
                doc = json.loads(await content.readall())
                
                stats["total_approved"] += 1
                
                rating = doc.get("rating", 0)
                if rating in stats["by_rating"]:
                    stats["by_rating"][rating] += 1
                
                for tag in doc.get("tags", []):
                    stats["by_tag"][tag] += 1
                
                approved_responses.append({
                    "id": doc.get("id"),
                    "usage_count": doc.get("usage_count", 0),
                    "rating": rating,
                    "user_query": doc.get("user_query", "")[:50]
                })
            
            # Sort by usage count
            approved_responses.sort(key=lambda x: x["usage_count"], reverse=True)
            stats["most_used"] = approved_responses[:10]
            
            # Convert Counter to dict
            stats["by_tag"] = dict(stats["by_tag"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting approved responses stats: {e}")
            return {}
    
    async def get_dashboard_data(self) -> Dict:
        """
        Get comprehensive dashboard data.
        
        Returns:
            Dictionary with all dashboard metrics
        """
        try:
            # Get data from last 30 days
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)
            
            # Gather all statistics
            conv_summary = await self.get_conversation_summary(start_date, end_date)
            feedback_summary = await self.get_feedback_summary(start_date, end_date)
            quality_trends = await self.get_quality_trends(days=30, interval_days=7)
            approved_stats = await self.get_approved_responses_stats()
            
            return {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": 30
                },
                "conversations": conv_summary,
                "feedback": feedback_summary,
                "quality_trends": quality_trends,
                "approved_responses": approved_stats,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {}
    
    async def close(self):
        """Close storage client."""
        if self.blob_service_client:
            await self.blob_service_client.close()


# Singleton instance
_analytics = None


def get_analytics(storage_connection_string: str = None) -> Analytics:
    """
    Get singleton instance of Analytics.
    
    Args:
        storage_connection_string: Azure Storage connection string (required on first call)
        
    Returns:
        Analytics instance
    """
    global _analytics
    if _analytics is None:
        if storage_connection_string is None:
            raise ValueError("storage_connection_string required for first initialization")
        _analytics = Analytics(storage_connection_string)
    return _analytics
