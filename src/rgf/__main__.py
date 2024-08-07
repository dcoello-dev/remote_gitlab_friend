import os
import sys
import gitlab
import argparse
from git import Repo
from pyfzf.pyfzf import FzfPrompt


class c:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    ORANGE = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    BACKSPACE = '\x08'

    @staticmethod
    def c(str: str, color: str) -> str:
        return color + str + c.ENDC


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


def print_mrs_human(mrs, _):
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


def branch_is_sync(local_repo, branch, origin="origin") -> bool:
    return local_repo.git.log(f"{origin}/{branch}..{branch}") == ""


def tree_to_format(tree: dict, local_repo, level=0) -> list:
    current_branch = local_repo.git.branch("--show-current")
    ret = []
    l_color = c.GREEN if level == 0 else c.ORANGE
    for k in tree.keys():
        try:
            sync = branch_is_sync(local_repo, k)
            s_color = c.CYAN if sync else c.RED
            s_simbol = "=" if sync else "~"
        except Exception:
            s_color = c.ORANGE
            s_simbol = "#"
        line = f"[{c.c(s_simbol, s_color)}][{c.c(str(level), l_color)}] {k}"
        if current_branch == k:
            line = f"{c.c('->', c.CYAN + c.BOLD)} {line}"
        ret.append(line)
        ret = ret + tree_to_format(tree[k], local_repo, level + 1)
    return ret


def format_mrs(mrs, local_repo) -> list:
    stree = dict()
    for mr in mrs:
        if mr.attributes['target_branch'] in ["main", "master", "develop"]:
            stree[mr.attributes["source_branch"]] = stack_tree(
                mrs, mr.attributes["source_branch"])
    return tree_to_format(stree, local_repo)


def print_mrs_fzf(mrs, local_repo):
    fzf = FzfPrompt()
    ret = fzf.prompt(format_mrs(mrs, local_repo), '--cycle --ansi')
    if ret == None or ret == []:
        sys.exit(1)
    return reverse_format(ret[0])


def checkout_to_branch(local_repo, branch: str):
    try:
        local_repo.git.checkout(branch)
    except Exception:
        id = local_repo.git.branch("--show-current")
        print(f"(stash push) -> {id}")
        local_repo.git.stash("push", "-m", id)
        local_repo.git.checkout(branch)
    print(f"(checkout) -> {branch}")
    st = recover_stash(local_repo, branch)
    if st is not None:
        print(f"(stash pop) -> {branch}")
        local_repo.git.stash("pop", st)


def get_mr_from_branch(branch, mrs):
    for mr in mrs:
        if mr.attributes['source_branch'] == branch:
            return mr
    return None


def rebase_stacked_branch(mrs, local_repo):
    branch = local_repo.git.branch("--show-current")
    mr = get_mr_from_branch(branch, mrs)
    if mr is not None:
        print(f"(stash push) -> {branch}")
        local_repo.git.stash("push", "-m", branch)
        os.system(f"git rebase -i {mr.attributes['target_branch']}")
        st = recover_stash(local_repo, branch)
        if st is not None:
            print(f"(stash pop) -> {branch}")
            local_repo.git.stash("pop", st)
    else:
        print("mr does not exist")
        sys.exit(1)


def recover_stash(local_repo, branch):
    for m in [s for s in local_repo.git.stash("list").split("\n") if "WIP" not in s]:
        cmp = m.split(":")
        if branch == cmp[2].strip():
            return cmp[0].strip()

    return None


parser = argparse.ArgumentParser(
    description="Get remote MR and checkout local repo to MR branch")

parser.add_argument(
    '-a', '--author',
    default=None,
    help="filter by author")

parser.add_argument(
    '-x', '--execute',
    default="checkout",
    help="action to execute on selected option")

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
    mrs = get_mrs(p, author=args.author)
    branch = output(mrs, repo[2])

    if args.execute == "checkout" and branch != None:
        checkout_to_branch(repo[2], branch)

    if args.execute == "rebase" and branch != None:
        checkout_to_branch(repo[2], branch)
        rebase_stacked_branch(mrs, repo[2])


if __name__ == "__main__":
    main()
