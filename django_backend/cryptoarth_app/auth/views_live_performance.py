"""
Live Strategy Performance APIs (Read-Only)
Step-10: Aggregates live executed trades for comparison with backtest

CRITICAL: Read-only aggregation only
NO computation, NO mutations, NO mixing with backtest data
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied, NotFound
from django.db.models import Sum, Count, Avg, Q, F, DecimalField
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

from .models import OrderDetails, tradeDetails, userStratergyPortfolio, highLowstratergy, User
from .permissions import IsStaff

logger = logging.getLogger(__name__)


def calculate_win_rate(winning_trades, total_trades):
    """Calculate win rate percentage"""
    if total_trades == 0:
        return 0.0
    return (winning_trades / total_trades) * 100


def calculate_max_drawdown(daily_pnl_list):
    """Calculate maximum drawdown from daily PnL"""
    if not daily_pnl_list:
        return 0.0
    
    cumulative = 0
    peak = 0
    max_dd = 0
    
    for pnl in daily_pnl_list:
        cumulative += float(pnl)
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_dd:
            max_dd = drawdown
    
    return max_dd


class LivePerformanceSummaryView(APIView):
    """
    GET /auth/strategy/{id}/live/performance/summary
    Returns aggregated live performance summary for a strategy
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        try:
            strategy_id = int(id)
        except ValueError:
            return Response(
                {"success": False, "error": "Invalid strategy ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get strategy
        try:
            strategy = highLowstratergy.objects.get(id=strategy_id)
        except highLowstratergy.DoesNotExist:
            return Response(
                {"success": False, "error": "Strategy not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check access: user must own or have access to this strategy
        user_has_access = userStratergyPortfolio.objects.filter(
            owner=request.user,
            stratergy=strategy,
            is_active=True
        ).exists()

        # Admin/vendor can access any strategy
        is_admin = request.user.is_staff or request.user.is_vendor

        if not user_has_access and not is_admin:
            raise PermissionDenied("You don't have access to this strategy")

        # Aggregate from OrderDetails (completed orders with profit)
        orders = OrderDetails.objects.filter(
            stratergy=str(strategy_id),
            status="Completed"
        )

        # If not admin, filter by user's trades only
        if not is_admin:
            orders = orders.filter(owner=request.user)

        # Calculate metrics
        total_orders = orders.count()
        
        if total_orders == 0:
            return Response({
                "success": True,
                "data": {
                    "net_pnl": 0,
                    "max_drawdown": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "avg_trade": 0,
                    "symbol": strategy.symbol if hasattr(strategy, 'symbol') else "N/A",
                    "timeframe": "Live",
                    "strategy_id": strategy_id
                }
            })

        # Aggregate profit
        total_profit = orders.aggregate(
            total=Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=3))
        )['total'] or Decimal('0')

        # Winning vs losing trades
        winning_trades = orders.filter(profit__gt=0).count()
        losing_trades = orders.filter(profit__lt=0).count()
        
        # Calculate profit factor
        gross_profit = orders.filter(profit__gt=0).aggregate(
            total=Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=3))
        )['total'] or Decimal('0')
        
        gross_loss = abs(orders.filter(profit__lt=0).aggregate(
            total=Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=3))
        )['total'] or Decimal('0'))
        
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0

        # Calculate max drawdown from daily PnL
        daily_pnl = orders.annotate(
            date=TruncDate('date')
        ).values('date').annotate(
            daily_profit=Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=3))
        ).order_by('date').values_list('daily_profit', flat=True)
        
        max_drawdown = calculate_max_drawdown(daily_pnl)

        # Average trade
        avg_trade = float(total_profit / total_orders) if total_orders > 0 else 0.0

        return Response({
            "success": True,
            "data": {
                "net_pnl": float(total_profit),
                "max_drawdown": max_drawdown,
                "win_rate": calculate_win_rate(winning_trades, total_orders),
                "profit_factor": profit_factor,
                "total_trades": total_orders,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "avg_trade": avg_trade,
                "symbol": strategy.symbol if hasattr(strategy, 'symbol') else "N/A",
                "timeframe": "Live",
                "strategy_id": strategy_id
            }
        })


class LivePerformanceDailyView(APIView):
    """
    GET /auth/strategy/{id}/live/performance/daily
    Returns daily cumulative PnL and drawdown for chart
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        try:
            strategy_id = int(id)
        except ValueError:
            return Response(
                {"success": False, "error": "Invalid strategy ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get strategy
        try:
            strategy = highLowstratergy.objects.get(id=strategy_id)
        except highLowstratergy.DoesNotExist:
            return Response(
                {"success": False, "error": "Strategy not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check access
        user_has_access = userStratergyPortfolio.objects.filter(
            owner=request.user,
            stratergy=strategy,
            is_active=True
        ).exists()
        is_admin = request.user.is_staff or request.user.is_vendor

        if not user_has_access and not is_admin:
            raise PermissionDenied("You don't have access to this strategy")

        # Aggregate daily PnL
        orders = OrderDetails.objects.filter(
            stratergy=str(strategy_id),
            status="Completed"
        )

        if not is_admin:
            orders = orders.filter(owner=request.user)

        # Group by date and calculate daily PnL
        daily_data = orders.annotate(
            date=TruncDate('date')
        ).values('date').annotate(
            daily_pnl=Sum('profit', output_field=DecimalField(max_digits=20, decimal_places=3))
        ).order_by('date')

        # Calculate cumulative PnL and drawdown
        cumulative_pnl = 0
        peak = 0
        result = []

        for entry in daily_data:
            daily_pnl = float(entry['daily_pnl'] or 0)
            cumulative_pnl += daily_pnl
            
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            
            drawdown = peak - cumulative_pnl if peak > 0 else 0

            result.append({
                "date": entry['date'].isoformat(),
                "cumulative_pnl": cumulative_pnl,
                "drawdown": drawdown,
                "daily_pnl": daily_pnl
            })

        return Response({
            "success": True,
            "data": result
        })


class LivePerformanceTradesView(APIView):
    """
    GET /auth/strategy/{id}/live/performance/trades
    Returns paginated trade-by-trade details
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        try:
            strategy_id = int(id)
        except ValueError:
            return Response(
                {"success": False, "error": "Invalid strategy ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get pagination params
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        limit = min(limit, 100)  # Max 100 per page
        offset = max(offset, 0)

        # Get strategy
        try:
            strategy = highLowstratergy.objects.get(id=strategy_id)
        except highLowstratergy.DoesNotExist:
            return Response(
                {"success": False, "error": "Strategy not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check access
        user_has_access = userStratergyPortfolio.objects.filter(
            owner=request.user,
            stratergy=strategy,
            is_active=True
        ).exists()
        is_admin = request.user.is_staff or request.user.is_vendor

        if not user_has_access and not is_admin:
            raise PermissionDenied("You don't have access to this strategy")

        # Get orders
        orders = OrderDetails.objects.filter(
            stratergy=str(strategy_id),
            status="Completed"
        )

        if not is_admin:
            orders = orders.filter(owner=request.user)

        # Total count
        total = orders.count()

        # Paginate
        orders_page = orders.order_by('-date')[offset:offset + limit]

        # Format trades
        trades = []
        for order in orders_page:
            # Determine entry/exit based on side
            if order.side.upper() == 'BUY':
                entry_price = float(order.buyprice)
                exit_price = float(order.sellprice)
                entry_time = order.date  # Approximate
                exit_time = order.date
            else:  # SELL
                entry_price = float(order.sellprice)
                exit_price = float(order.buyprice)
                entry_time = order.date
                exit_time = order.date

            pnl = float(order.profit)
            pnl_percent = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            trades.append({
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "side": order.side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "exit_reason": "Completed",
                "symbol": order.symbol,
                "order_id": order.orderid
            })

        return Response({
            "success": True,
            "data": trades,
            "total": total,
            "limit": limit,
            "offset": offset
        })

