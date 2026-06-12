#!/usr/bin/env python
"""
Script de Restauração de Banco de Dados Criptografado.
Lê o arquivo criptografado, descriptografa em memória e restaura no container Docker.
"""
import os
import sys
import subprocess
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
    if len(sys.argv) < 2:
        print("Erro: Forneça o caminho do arquivo de backup criptografado (.enc).", file=sys.stderr)
        print("Uso: python scripts/restaurar_db.py backups/NOME_DO_ARQUIVO.pgdump.enc", file=sys.stderr)
        sys.exit(1)
        
    backup_path = sys.argv[1]
    if not os.path.exists(backup_path):
        print(f"Erro: Arquivo de backup não encontrado em: {backup_path}", file=sys.stderr)
        sys.exit(1)
        
    env = carregar_env()
    db_user = env.get("POSTGRES_USER")
    db_name = env.get("POSTGRES_DB")
    enc_key = env.get("BACKUP_ENCRYPTION_KEY")
    
    if not db_user or not db_name:
        print("Erro: POSTGRES_USER e POSTGRES_DB precisam estar definidos no .env.", file=sys.stderr)
        sys.exit(1)
        
    if not enc_key:
        print("Erro: BACKUP_ENCRYPTION_KEY não está configurada no .env.", file=sys.stderr)
        sys.exit(1)
        
    try:
        fernet = Fernet(enc_key.encode())
    except Exception as e:
        print(f"Erro ao inicializar chave de criptografia: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Lendo e descriptografando arquivo de backup: {backup_path}...")
    try:
        with open(backup_path, "rb") as f:
            encrypted_data = f.read()
            
        decrypted_data = fernet.decrypt(encrypted_data)
        print("Descriptografia concluída com sucesso em memória. Iniciando restauração no Docker...")
        
        # Executa pg_restore enviando os bytes via stdin
        # --clean limpa os objetos existentes antes de recriar
        # --if-exists evita erros se as tabelas ainda não existirem
        cmd = ["docker", "compose", "exec", "-T", "db", "pg_restore", "-U", db_user, "-d", db_name, "--clean", "--if-exists"]
        
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=decrypted_data)
        
        if process.returncode == 0:
            print("Restauração de banco de dados concluída com sucesso!")
        else:
            print("Erro durante a restauração do banco de dados:", file=sys.stderr)
            print(stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            sys.exit(process.returncode)
            
    except Exception as e:
        print(f"Erro inesperado durante a restauração: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
