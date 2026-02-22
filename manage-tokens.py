#!/usr/bin/env python3
"""
Token management CLI for SMS API
"""

import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta
import argparse

DB_PATH = '/opt/sms-api/tokens.db'

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def create_token(name, days=None, max_hour=5, max_day=10):
    """Create new API token"""
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    
    expires_at = None
    if days:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO tokens (token_hash, name, created_at, expires_at, 
                                         max_sms_per_hour, max_sms_per_day, enabled)
                     VALUES (?, ?, ?, ?, ?, ?, 1)''',
                  (token_hash, name, datetime.now().isoformat(), expires_at,
                   max_hour, max_day))
        conn.commit()
        token_id = c.lastrowid
        
        print(f"✅ Token created!")
        print(f"   ID: {token_id}")
        print(f"   Name: {name}")
        print(f"   Token: {token}")
        print(f"   Expires: {expires_at or 'Never'}")
        print(f"   Limits: {max_hour}/hour, {max_day}/day")
        print(f"\n⚠️  SAVE THIS TOKEN - it won't be shown again!")
        
    except sqlite3.IntegrityError:
        print("❌ Token already exists")
    finally:
        conn.close()

def list_tokens():
    """List all tokens"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT id, name, created_at, expires_at, max_sms_per_hour, 
                        max_sms_per_day, enabled FROM tokens ORDER BY id''')
    
    tokens = c.fetchall()
    conn.close()
    
    if not tokens:
        print("No tokens found")
        return
    
    print(f"\n{'ID':<5} {'Name':<20} {'Created':<20} {'Expires':<20} {'Limits':<15} {'Status':<8}")
    print("-" * 100)
    
    for row in tokens:
        token_id, name, created, expires, max_h, max_d, enabled = row
        created_dt = datetime.fromisoformat(created).strftime("%Y-%m-%d %H:%M")
        expires_str = datetime.fromisoformat(expires).strftime("%Y-%m-%d") if expires else "Never"
        limits = f"{max_h}/h, {max_d}/d"
        status = "✅ Active" if enabled else "❌ Disabled"
        
        print(f"{token_id:<5} {name:<20} {created_dt:<20} {expires_str:<20} {limits:<15} {status:<8}")

def revoke_token(token_id):
    """Revoke (disable) token"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('UPDATE tokens SET enabled = 0 WHERE id = ?', (token_id,))
    conn.commit()
    
    if c.rowcount > 0:
        print(f"✅ Token {token_id} revoked")
    else:
        print(f"❌ Token {token_id} not found")
    
    conn.close()

def get_stats(token_id=None):
    """Get usage statistics"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if token_id:
        c.execute('''SELECT COUNT(*), 
                            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END)
                     FROM sms_log WHERE token_id = ?''', (token_id,))
        total, sent = c.fetchone()
        
        c.execute('SELECT name FROM tokens WHERE id = ?', (token_id,))
        name = c.fetchone()[0]
        
        print(f"\nToken: {name} (ID: {token_id})")
        print(f"  Total SMS: {total}")
        print(f"  Sent: {sent}")
        print(f"  Failed: {total - sent}")
    else:
        c.execute('''SELECT COUNT(*), 
                            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END)
                     FROM sms_log''')
        total, sent = c.fetchone()
        
        print(f"\nGlobal Statistics:")
        print(f"  Total SMS: {total or 0}")
        print(f"  Sent: {sent or 0}")
        print(f"  Failed: {(total or 0) - (sent or 0)}")
    
    conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SMS API Token Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create token
    create_parser = subparsers.add_parser('create', help='Create new token')
    create_parser.add_argument('name', help='Token name/description')
    create_parser.add_argument('--days', type=int, help='Expiry in days (default: never)')
    create_parser.add_argument('--max-hour', type=int, default=5, help='Max SMS per hour (default: 5)')
    create_parser.add_argument('--max-day', type=int, default=10, help='Max SMS per day (default: 10)')
    
    # List tokens
    subparsers.add_parser('list', help='List all tokens')
    
    # Revoke token
    revoke_parser = subparsers.add_parser('revoke', help='Revoke token')
    revoke_parser.add_argument('id', type=int, help='Token ID')
    
    # Stats
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.add_argument('--token', type=int, help='Token ID (optional)')
    
    args = parser.parse_args()
    
    if args.command == 'create':
        create_token(args.name, args.days, args.max_hour, args.max_day)
    elif args.command == 'list':
        list_tokens()
    elif args.command == 'revoke':
        revoke_token(args.id)
    elif args.command == 'stats':
        get_stats(args.token)
    else:
        parser.print_help()
