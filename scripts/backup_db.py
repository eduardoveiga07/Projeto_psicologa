#!/usr/bin/env python
"""
Script de Backup Criptografado do Banco de Dados.
Executa o pg_dump do container Docker, criptografa em memória e salva no host.
Mantém rotação automática.
"""
import os
import sys
import subprocess
import glob
from datetime import datetime
from cryptography.fernet import Fernet

def carregar_env():
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars

def main():
    env = carregar_env()
    
    # Parâmetros
    db_user = env.get("POSTGRES_USER")
    db_name = env.get("POSTGRES_DB")
    backup_dir = env.get("BACKUP_DIR", "backups")
    enc_key = env.get("BACKUP_ENCRYPTION_KEY")
    retention_count = int(env.get("BACKUP_RETENTION_COUNT", "7"))
    
    if not db_user or not db_name:
        print("Erro: POSTGRES_USER e POSTGRES_DB precisam estar definidos no .env.", file=sys.stderr)
        sys.exit(1)
        
    if not enc_key:
        nova_chave = Fernet.generate_key().decode()
        print("Erro: BACKUP_ENCRYPTION_KEY não definida no .env.", file=sys.stderr)
        print("Por favor, adicione a seguinte chave ao seu arquivo .env para habilitar backups criptografados:", file=sys.stderr)
        print(f"\nBACKUP_ENCRYPTION_KEY={nova_chave}\n", file=sys.stderr)
        sys.exit(1)
        
    # Inicializa Fernet
    try:
        fernet = Fernet(enc_key.encode())
    except Exception as e:
        print(f"Erro ao inicializar chave de criptografia: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Cria pasta de backup
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{db_name}_backup_{timestamp}.pgdump.enc"
    output_path = os.path.join(backup_dir, output_filename)
    
    print(f"Iniciando backup criptografado do banco de dados '{db_name}'...")
    
    # Executa pg_dump no container db e captura o binário
    cmd = ["docker", "compose", "exec", "-T", "db", "pg_dump", "-U", db_user, "-d", db_name, "-F", "c"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        dump_data = result.stdout
        
        if not dump_data:
            print("Erro: O dump gerado está vazio.", file=sys.stderr)
            sys.exit(1)
            
        print("Criptografando dados em memória...")
        encrypted_data = fernet.encrypt(dump_data)
        
        print(f"Gravando arquivo criptografado em: {output_path}")
        with open(output_path, "wb") as f:
            f.write(encrypted_data)
            
        print("Backup concluído com sucesso!")
        
        # Rotação de backups antigos
        backup_pattern = os.path.join(backup_dir, f"{db_name}_backup_*.pgdump.enc")
        arquivos = sorted(glob.glob(backup_pattern))
        
        if len(arquivos) > retention_count:
            excesso = arquivos[:-retention_count]
            for arq in excesso:
                try:
                    os.remove(arq)
                    print(f"Removido backup antigo excedente: {arq}")
                except Exception as ex:
                    print(f"Aviso: Não foi possível remover {arq}. Erro: {ex}", file=sys.stderr)
                    
    except subprocess.CalledProcessError as e:
        print("Erro crítico ao executar pg_dump no contêiner Docker:", file=sys.stderr)
        print(e.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Erro inesperado durante o backup: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
