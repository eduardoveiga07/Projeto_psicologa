#!/usr/bin/env python
"""
Script de Teste de Restauração Periódica.
Valida se o backup mais recente pode ser descriptografado e restaurado
em um banco de dados temporário de teste para garantir a integridade estrutural.
"""
import os
import sys
import glob
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
    env = carregar_env()
    db_user = env.get("POSTGRES_USER")
    db_name = env.get("POSTGRES_DB")
    backup_dir = env.get("BACKUP_DIR", "backups")
    enc_key = env.get("BACKUP_ENCRYPTION_KEY")
    
    if not db_user or not db_name:
        print("Erro: POSTGRES_USER e POSTGRES_DB precisam estar definidos no .env.", file=sys.stderr)
        sys.exit(1)
        
    if not enc_key:
        print("Erro: BACKUP_ENCRYPTION_KEY não definida no .env.", file=sys.stderr)
        sys.exit(1)
        
    # Encontra o backup mais recente
    backup_pattern = os.path.join(backup_dir, f"{db_name}_backup_*.pgdump.enc")
    arquivos = sorted(glob.glob(backup_pattern))
    
    if not arquivos:
        print(f"Erro: Nenhum arquivo de backup encontrado correspondendo ao padrão: {backup_pattern}", file=sys.stderr)
        sys.exit(1)
        
    backup_alvo = arquivos[-1]
    print(f"Backup mais recente identificado para teste: {backup_alvo}")
    
    try:
        fernet = Fernet(enc_key.encode())
    except Exception as e:
        print(f"Erro ao inicializar chave de criptografia: {e}", file=sys.stderr)
        sys.exit(1)
        
    print("Descriptografando backup em memória...")
    try:
        with open(backup_alvo, "rb") as f:
            encrypted_data = f.read()
        decrypted_data = fernet.decrypt(encrypted_data)
    except Exception as e:
        print(f"Erro crítico: Falha ao descriptografar o backup. Chave incorreta ou arquivo corrompido! Detalhes: {e}", file=sys.stderr)
        sys.exit(1)
        
    test_db = "consultorio_teste_backup"
    print(f"Criando banco de dados temporário de testes '{test_db}' no PostgreSQL...")
    
    # Prepara comandos no postgres para resetar o banco de teste
    cmd_drop = ["docker", "compose", "exec", "-T", "db", "psql", "-U", db_user, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {test_db} WITH (FORCE);"]
    cmd_create = ["docker", "compose", "exec", "-T", "db", "psql", "-U", db_user, "-d", "postgres", "-c", f"CREATE DATABASE {test_db};"]
    
    try:
        subprocess.run(cmd_drop, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.run(cmd_create, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        print(f"Restaurando o dump em '{test_db}'...")
        cmd_restore = ["docker", "compose", "exec", "-T", "db", "pg_restore", "-U", db_user, "-d", test_db]
        
        process = subprocess.Popen(cmd_restore, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=decrypted_data)
        
        if process.returncode != 0:
            print("Erro durante a restauração do banco de testes:", file=sys.stderr)
            print(stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            sys.exit(process.returncode)
            
        print("Validação: Executando consulta básica no banco restaurado...")
        cmd_check = ["docker", "compose", "exec", "-T", "db", "psql", "-U", db_user, "-d", test_db, "-c", "SELECT COUNT(*) FROM usuarios;"]
        check_res = subprocess.run(cmd_check, capture_output=True, text=True, check=True)
        
        print("Retorno da verificação estrutural (Tabela 'usuarios'):")
        print(check_res.stdout.strip())
        
        print("\n>>> SUCESSO: O teste de restauração foi concluído com êxito! O arquivo de backup é íntegro. <<<")
        
    except subprocess.CalledProcessError as e:
        print("Erro durante a execução de comandos do PostgreSQL:", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        sys.exit(1)
    finally:
        print(f"Removendo banco de dados temporário '{test_db}'...")
        try:
            subprocess.run(cmd_drop, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

if __name__ == "__main__":
    main()
