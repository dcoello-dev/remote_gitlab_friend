
import os
import sys
import gitlab
import argparse
from git import Repo
from pyfzf.pyfzf import FzfPrompt


def local_repo(path=".", ssh=False) -> tuple:
    pt = ["https://", "git@"]
    try:
        local_repo = Repo(path)
        repo = local_repo.remotes.origin.url.split(":")
        return f'{pt[ssh]}{repo[0].split("@")[1]}', repo[1].split(".git")[0], local_repo
    except Exception:
        print("you are not in a valid git repo")
        sys.exit(1)


def get_token(env_v="GITLAB_API_TOKEN") -> str:
    var = os.environ[env_v]
    if var == "":
        print("GITLAB_API_TOKEN env var not defined")
        sys.exit(1)
    return var


def init_gitlab(repo: str, token: str) -> gitlab.Gitlab:
    gl = gitlab.Gitlab(repo, private_token=token)
    gl.auth()
    return gl


def remote_repo(repo: str, remote: gitlab.Gitlab):
    return remote.projects.get(repo)


def get_mrs(project, author=None, state="opened") -> list:
    ret = list(project.mergerequests.list(state=state))
    return ret if author == None else [m for m in ret if m.attributes["author"]["username"] == author]


def print_mrs_human(mrs):
    for mr in mrs:
        print(
            f'({mr.attributes["author"]["username"]}): {mr.attributes["title"]} ')
        print(f'\tsource: {mr.attributes["source_branch"]}')
        print(f'\ttarget: {mr.attributes["target_branch"]}')
    return None


def format_line(mr) -> str:
    atts = mr.attributes
    return f"{atts['title'].split(' ')[0]}: {atts['source_branch']} -> {atts['target_branch']}"


def reverse_format(line) -> str:
    return line.split(" ")[1]


def stack_tree(mrs, target) -> dict:
    ret = dict()
    for mr in mrs:
        if mr.attributes["target_branch"] == target:
            ret[mr.attributes["source_branch"]] = stack_tree(
                mrs, mr.attributes["source_branch"])
    return ret


def tree_to_format(tree: dict, level=0) -> list:
    ret = []
    for k in tree.keys():
        ret.append(f"[{level}] {k}")
        ret = ret + tree_to_format(tree[k], level + 1)
    return ret


def format_mrs(mrs) -> list:
    stree = dict()
    for mr in mrs:
        if mr.attributes['target_branch'] in ["main", "master", "develop"]:
            stree[mr.attributes["source_branch"]] = stack_tree(
                mrs, mr.attributes["source_branch"])
    return tree_to_format(stree)


def print_mrs_fzf(mrs):
    fzf = FzfPrompt()
    ret = fzf.prompt(format_mrs(mrs), '--cycle')
    if ret == None or ret == []:
        sys.exit(1)
    return reverse_format(ret[0])


def checkout_to_branch(local_repo, branch: str):
    print(f"(checkout) -> {branch}")
    local_repo.git.checkout(branch)


parser = argparse.ArgumentParser(
    description="Get remote MR and checkout local repo to MR branch")

parser.add_argument(
    '-a', '--author',
    default=None,
    help="filter by author")

parser.add_argument(
    '-f', '--fzf',
    default=False,
    action="store_true",
    help="output fzf or human readable")

args = parser.parse_args()


def main():
    output = print_mrs_human
    if args.fzf:
        output = print_mrs_fzf

    repo = local_repo()
    gl = init_gitlab(repo[0], get_token())
    p = remote_repo(repo[1], gl)
    branch = output(get_mrs(p, author=args.author))

    if branch != None:
        checkout_to_branch(repo[2], branch)


if __name__ == "__main__":
    main()
