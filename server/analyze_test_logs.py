#!/usr/bin/env python3
"""
Analisi Test Logs - Script di Esempio

Questo script dimostra come analizzare i test logs salvati su Azure Storage.
Fornisce funzioni per calcolare metriche aggregate e identificare trend.

Requisiti:
- azure-storage-blob
- python-dotenv

Utilizzo:
    python analyze_test_logs.py
"""

import os
import json
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Carica variabili d'ambiente
load_dotenv()

def get_blob_service_client():
    """Crea client per Azure Blob Storage."""
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING non configurata")
    return BlobServiceClient.from_connection_string(connection_string)

def load_all_test_logs():
    """Carica tutti i test logs dal container."""
    blob_service_client = get_blob_service_client()
    container_client = blob_service_client.get_container_client("testlogs")
    
    test_logs = []
    for blob in container_client.list_blobs():
        blob_client = container_client.get_blob_client(blob.name)
        content = blob_client.download_blob().readall()
        test_data = json.loads(content)
        test_data['blob_name'] = blob.name
        test_logs.append(test_data)
    
    # Ordina per timestamp
    test_logs.sort(key=lambda x: x['timestamp'])
    return test_logs

def calculate_average_metrics(test_logs):
    """Calcola metriche medie su tutti i test."""
    if not test_logs:
        return None
    
    total_accuracy = 0
    total_context_retention = 0
    total_manipulation_resistance = 0
    total_critical_issues = 0
    
    for test in test_logs:
        metrics = test['metrics']
        total_accuracy += metrics['accuracy']
        total_context_retention += metrics['contextRetention']
        total_manipulation_resistance += metrics['manipulationResistance']
        total_critical_issues += test['summary']['criticalIssuesCount']
    
    count = len(test_logs)
    return {
        'average_accuracy': round(total_accuracy / count, 2),
        'average_context_retention': round(total_context_retention / count, 2),
        'average_manipulation_resistance': round(total_manipulation_resistance / count, 2),
        'total_critical_issues': total_critical_issues,
        'average_critical_issues': round(total_critical_issues / count, 2),
        'total_tests': count
    }

def analyze_by_user_type(test_logs):
    """Analizza performance per tipo utente."""
    user_type_stats = defaultdict(lambda: {
        'total_dialogs': 0,
        'total_turns': 0,
        'successful_turns': 0,
        'context_breaks': 0,
        'critical_issues': 0
    })
    
    for test in test_logs:
        for dialog in test['dialogs']:
            user_type = dialog['userType']
            stats = user_type_stats[user_type]
            
            stats['total_dialogs'] += 1
            stats['total_turns'] += len(dialog['turns'])
            stats['successful_turns'] += dialog['analysis']['successfulTurns']
            stats['context_breaks'] += dialog['analysis']['contextBreaks']
            if dialog['analysis']['criticalIssue']:
                stats['critical_issues'] += 1
    
    # Calcola percentuali
    results = {}
    for user_type, stats in user_type_stats.items():
        success_rate = (stats['successful_turns'] / stats['total_turns'] * 100) if stats['total_turns'] > 0 else 0
        results[user_type] = {
            'total_dialogs': stats['total_dialogs'],
            'total_turns': stats['total_turns'],
            'success_rate': round(success_rate, 2),
            'context_breaks': stats['context_breaks'],
            'critical_issues': stats['critical_issues']
        }
    
    return results

def find_critical_issues(test_logs):
    """Trova tutti i problemi critici."""
    critical_issues = []
    
    for test in test_logs:
        if test['summary']['criticalIssuesCount'] > 0:
            for issue in test['criticalIssues']:
                critical_issues.append({
                    'timestamp': test['timestamp'],
                    'blob_name': test['blob_name'],
                    'dialog': issue['dialog'],
                    'user_type': issue['type'],
                    'issue': issue['issue']
                })
    
    return critical_issues

def analyze_trends(test_logs):
    """Analizza trend nel tempo."""
    if len(test_logs) < 2:
        return None
    
    # Ordina per timestamp
    sorted_tests = sorted(test_logs, key=lambda x: x['timestamp'])
    
    # Confronta primo e ultimo test
    first = sorted_tests[0]
    last = sorted_tests[-1]
    
    accuracy_change = last['metrics']['accuracy'] - first['metrics']['accuracy']
    context_change = last['metrics']['contextRetention'] - first['metrics']['contextRetention']
    
    return {
        'first_test_date': first['timestamp'],
        'last_test_date': last['timestamp'],
        'total_tests': len(test_logs),
        'accuracy_trend': f"{'+' if accuracy_change >= 0 else ''}{accuracy_change}%",
        'context_retention_trend': f"{'+' if context_change >= 0 else ''}{context_change}%"
    }

def print_report(test_logs):
    """Stampa report completo."""
    print("=" * 80)
    print("REPORT ANALISI TEST LOGS")
    print("=" * 80)
    print()
    
    # Metriche medie
    print("📊 METRICHE MEDIE")
    print("-" * 80)
    avg_metrics = calculate_average_metrics(test_logs)
    if avg_metrics:
        print(f"Numero totale test: {avg_metrics['total_tests']}")
        print(f"Accuratezza media: {avg_metrics['average_accuracy']}%")
        print(f"Mantenimento contesto medio: {avg_metrics['average_context_retention']}%")
        print(f"Resistenza manipolazione media: {avg_metrics['average_manipulation_resistance']}%")
        print(f"Problemi critici totali: {avg_metrics['total_critical_issues']}")
        print(f"Problemi critici medi per test: {avg_metrics['average_critical_issues']}")
    else:
        print("Nessun test trovato")
    print()
    
    # Analisi per tipo utente
    print("👥 ANALISI PER TIPO UTENTE")
    print("-" * 80)
    user_type_analysis = analyze_by_user_type(test_logs)
    type_labels = {
        'collaborative': '✅ Collaborativo',
        'offtopic': '❌ Fuori Tema',
        'malicious': '⚠️  Malevolo'
    }
    for user_type, stats in user_type_analysis.items():
        label = type_labels.get(user_type, user_type)
        print(f"\n{label}:")
        print(f"  Dialoghi totali: {stats['total_dialogs']}")
        print(f"  Turni totali: {stats['total_turns']}")
        print(f"  Tasso di successo: {stats['success_rate']}%")
        print(f"  Perdite contesto: {stats['context_breaks']}")
        print(f"  Problemi critici: {stats['critical_issues']}")
    print()
    
    # Problemi critici
    print("🚨 PROBLEMI CRITICI")
    print("-" * 80)
    critical_issues = find_critical_issues(test_logs)
    if critical_issues:
        print(f"Totale problemi critici trovati: {len(critical_issues)}\n")
        for idx, issue in enumerate(critical_issues, 1):
            print(f"{idx}. [{issue['timestamp']}] Dialogo #{issue['dialog']} ({issue['user_type']})")
            print(f"   {issue['issue']}")
            print(f"   File: {issue['blob_name']}")
            print()
    else:
        print("Nessun problema critico trovato ✅")
    print()
    
    # Trend
    print("📈 TREND NEL TEMPO")
    print("-" * 80)
    trends = analyze_trends(test_logs)
    if trends:
        print(f"Primo test: {trends['first_test_date']}")
        print(f"Ultimo test: {trends['last_test_date']}")
        print(f"Numero test: {trends['total_tests']}")
        print(f"Variazione accuratezza: {trends['accuracy_trend']}")
        print(f"Variazione mantenimento contesto: {trends['context_retention_trend']}")
    else:
        print("Dati insufficienti per analisi trend (servono almeno 2 test)")
    print()
    
    print("=" * 80)

def export_summary_to_json(test_logs, output_file="test_summary.json"):
    """Esporta sommario in formato JSON."""
    summary = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'average_metrics': calculate_average_metrics(test_logs),
        'user_type_analysis': analyze_by_user_type(test_logs),
        'critical_issues': find_critical_issues(test_logs),
        'trends': analyze_trends(test_logs),
        'test_count': len(test_logs)
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Sommario esportato in: {output_file}")

def main():
    """Funzione principale."""
    try:
        print("Caricamento test logs da Azure Storage...")
        test_logs = load_all_test_logs()
        
        if not test_logs:
            print("⚠️  Nessun test log trovato nel container 'testlogs'")
            return
        
        print(f"✅ Caricati {len(test_logs)} test logs\n")
        
        # Stampa report
        print_report(test_logs)
        
        # Esporta sommario
        export_summary_to_json(test_logs)
        
    except Exception as e:
        print(f"❌ Errore: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
